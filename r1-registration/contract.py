"""Hash-bound draft measurement contract and offline evidence evaluation; never launch authority."""
from dataclasses import asdict
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
sys.path.insert(0,str(REPO/'r1-service'))
import integrated_common
from capture import CaptureError, Limits, canonical, digest, exclusive_file, private_directory, strict_json
from handoff import path_without_links, read_private
from session_bundle import restore_session

LOCAL_CRITERIA={'minimum_selected_creations':24,'maximum_local_send_return_ns':1000000000,
                'maximum_gaps':0,'maximum_abandoned_sends':0,'maximum_unresolved_sends':0,
                'maximum_selected_without_completed_send':0}
UNKNOWN=('provider_acknowledged_subscriptions','external_creation_denominator',
         'initial_trade_coverage','billed_events','data_fees_lamports')
UNVERIFIED=('ledger_order_verified','finality_verified','profitability_evaluated')
HEX=re.compile(r'[0-9a-f]{64}\Z')


def pins():
    result=integrated_common.pins()
    for pattern in ('*.py','*.json','*.md'):
        for path in ROOT.glob(pattern):
            if path.is_symlink(): raise CaptureError('contract-source-link')
            result[str(path.relative_to(REPO))]=digest(path.read_bytes())
    return dict(sorted(result.items()))


def proposal():
    raw=(ROOT/'proposal.json').read_bytes()
    if len(raw)>8192: raise CaptureError('contract-proposal-bound')
    row=strict_json(raw)
    validate_proposal(row)
    return row


def validate_proposal(row):
    expected={'schema_version':1,'purpose':'source-feasibility-measurement-only',
        'approval_status':'draft-unapproved','limits':asdict(Limits()),'local_criteria':LOCAL_CRITERIA,
        'exposure':{'funding_ceiling_lamports':None,'intended_data_fee_ceiling_lamports':None,
                    'approved_exposed_balance_lamports':None,'owner_approved':False},
        'retention_policy_accepted':False,'production_rollout_accepted':False,'live_launch_authorized':False}
    # Canonical comparison distinguishes bool from int and rejects extra fields.
    if canonical(row)!=canonical(expected): raise CaptureError('contract-proposal-mismatch')
    Limits(**row['limits']).validate()


def freeze(directory):
    directory=path_without_links(directory);private_directory(directory)
    before=pins()
    row={'schema_version':1,'kind':'r1-offline-measurement-contract-draft-v1',
         'proposal':proposal(),'source_sha256':before,'source_digest':digest(canonical(before).encode())}
    raw=(canonical(row)+'\n').encode()
    if before!=pins(): raise CaptureError('contract-source-changed')
    exclusive_file(directory/'contract.json',raw)
    return {'contract_sha256':digest(raw),'contract_bytes':len(raw),'live_launch_authorized':False}


def load(path,expected_sha256):
    if not isinstance(expected_sha256,str) or not HEX.fullmatch(expected_sha256):
        raise CaptureError('contract-hash')
    raw=read_private(path_without_links(path),65536)
    if digest(raw)!=expected_sha256: raise CaptureError('contract-hash-mismatch')
    try: row=strict_json(raw)
    except (ValueError,UnicodeError): raise CaptureError('contract-json') from None
    if (not isinstance(row,dict) or set(row)!={'schema_version','kind','proposal','source_sha256','source_digest'}
            or type(row['schema_version']) is not int or row['schema_version']!=1
            or row['kind']!='r1-offline-measurement-contract-draft-v1'
            or (canonical(row)+'\n').encode()!=raw):
        raise CaptureError('contract-schema')
    validate_proposal(row['proposal'])
    expected=pins()
    if row['source_sha256']!=expected or row['source_digest']!=digest(canonical(expected).encode()):
        raise CaptureError('contract-source-mismatch')
    return row


def assess(measured,actual_limits,registered):
    """Internal evaluator of replayed local metrics; no remote facts accepted here."""
    validate_proposal(registered)
    if (measured.get('status')!='local-measurement-replayed-live-blocked'
            or any(measured.get(k,'missing') is not None for k in UNKNOWN)
            or any(measured.get(k) is not False for k in UNVERIFIED)):
        raise CaptureError('contract-unsupported-evidence')
    counters=('selected_creations','send_intents','local_sends_completed','send_intents_abandoned',
              'send_intents_without_completion_or_abandonment','selected_without_completed_subscription_send',
              'gaps','creation_records_observed','unique_creation_mints_observed','messages_counted','raw_rows')
    for key in counters:
        if type(measured.get(key)) is not int or not 0<=measured[key]<=20000:
            raise CaptureError('contract-count')
    selected=measured['selected_creations'];completed=measured['local_sends_completed']
    delay=measured['creation_receive_to_local_send_return_ns']
    if (not isinstance(delay,dict) or set(delay)!={'count','min','max','sum'}
            or type(delay['count']) is not int or not 0<=delay['count']<=completed
            or selected!=delay['count']+measured['selected_without_completed_subscription_send']
            or measured['send_intents']!=completed+measured['send_intents_abandoned']+measured['send_intents_without_completion_or_abandonment']
            or selected>measured['unique_creation_mints_observed']
            or measured['unique_creation_mints_observed']>measured['creation_records_observed']
            or measured['creation_records_observed']>measured['raw_rows']
            or measured['raw_rows']>measured['messages_counted']):
        raise CaptureError('contract-denominator')
    if (type(delay['sum']) is not int or delay['sum']<0
            or not delay['count'] and delay!={'count':0,'min':None,'max':None,'sum':0}
            or delay['count'] and (type(delay['min']) is not int or type(delay['max']) is not int
                or not 0<=delay['min']<=delay['max']
                or not delay['min']*delay['count']<=delay['sum']<=delay['max']*delay['count'])):
        raise CaptureError('contract-latency')
    Limits(**actual_limits).validate()
    criteria=registered['local_criteria']; failures=[];insufficient=[]
    if measured['session_outcome']!='capture-stopped': failures.append('session-not-cleanly-stopped')
    for key,limit in (('gaps','maximum_gaps'),('send_intents_abandoned','maximum_abandoned_sends'),
        ('send_intents_without_completion_or_abandonment','maximum_unresolved_sends'),
        ('selected_without_completed_subscription_send','maximum_selected_without_completed_send')):
        if measured[key]>criteria[limit]: failures.append(key)
    if delay['count'] and delay['max']>criteria['maximum_local_send_return_ns']:
        failures.append('local-send-return-latency')
    if selected<criteria['minimum_selected_creations']: insufficient.append('selected-sample-too-small')
    if actual_limits!=registered['limits']: insufficient.append('capture-limits-differ-from-contract')
    local='fail' if failures else 'insufficient' if insufficient else 'pass'
    return {'local_quality_verdict':local,'local_failures':failures,'local_insufficient':insufficient,
        'local_completion_fraction':{'numerator':delay['count'],'denominator':selected},
        'observed_creation_records':measured['creation_records_observed'],
        'observed_unique_creation_mints':measured['unique_creation_mints_observed'],
        'local_receive_to_send_return_ns':delay,
        'latency_scope':'capture-thread queue consumption to local send completion; excludes upstream-to-queue delay',
        'provider_evidence':{k:None for k in UNKNOWN},'source_adequacy_verdict':'insufficient',
        'measurement_gate_verdict':'fail' if failures else 'insufficient',
        'activation_blockers':['draft-not-owner-approved','provider-acknowledgement-unknown',
            'external-coverage-unknown','initial-trade-coverage-unknown','ledger-order-and-finality-unverified',
            'billing-and-exposed-balance-unapproved','production-rollout-unaccepted','live-retention-unaccepted'],
        'live_launch_authorized':False,'full_gate_accepted':False,'profitability_evaluated':False}


def review(contract_path,contract_sha256,bundle,bundle_sha256,output):
    registered=load(contract_path,contract_sha256)
    restored=restore_session(bundle,bundle_sha256,output)
    # Read the replay-validated start record, not a caller-supplied limits label.
    journal=read_private(Path(output)/'session.jsonl',8*1024**2)
    first=strict_json(journal.splitlines()[0]);actual_limits=first['payload']['limits']
    result=assess(restored['measurement'],actual_limits,registered['proposal'])
    result.update(contract_sha256=contract_sha256,session_bundle_sha256=restored['bundle_sha256'],
                  session_bundle_bytes=restored['bundle_bytes'],measurement=restored['measurement'],
                  capture=restored['capture'],complete_session_independently_replayed=True,
                  precollection_registration_proven=False)
    # A retrospective replay is not proof that this draft governed collection.
    load(contract_path,contract_sha256)
    exclusive_file(Path(output)/'evaluation.json',(canonical(result)+'\n').encode())
    return result
