"""One-attempt OFFLINE run joining admission, handoff, cleanup and verified preservation."""
import os
from pathlib import Path
import signal
import sys
import tempfile

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
sys.path.insert(0,str(REPO/'r1-preservation'))
import preserve
import contract
import lifecycle
from capture import CaptureError,canonical,digest,exclusive_file,private_directory,strict_json
from handoff import path_without_links,read_private
from supervisor import owner_lock
from integrated_backend import Backend,reap

SCENARIOS=('normal','cleanup-failure','shutdown-interruption')


def pins():
    result=preserve.pins()
    for pattern in ('*.py','*.md'):
        for path in ROOT.glob(pattern):
            if path.is_symlink():raise CaptureError('orchestration-source-link')
            result[str(path.relative_to(REPO))]=digest(path.read_bytes())
    return dict(sorted(result.items()))


def write(directory,name,row):
    raw=(canonical(row)+'\n').encode();exclusive_file(directory/name,raw);return digest(raw)


def read(directory,name,cap=65536):
    raw=read_private(directory/name,cap);row=strict_json(raw)
    if (canonical(row)+'\n').encode()!=raw:raise CaptureError('orchestration-noncanonical')
    return row,digest(raw)


def cleanup_valid(row,pipe_only):
    actors=row.get('actors',[])
    if (row.get('broker_reaped') is not True or not 2<=len(actors)<=3
            or row.get('provider_connections_opened')!=0 or row.get('production_modified') is not False
            or row.get('max_simultaneous_synthetic_owners')!=1):
        raise CaptureError('orchestration-cleanup-unconfirmed')
    for actor in actors:
        if actor['process_reaped'] is not True:raise CaptureError('orchestration-cleanup-unconfirmed')
        container=actor['container']
        if pipe_only:
            if container is not None:raise CaptureError('orchestration-transport-mismatch')
        elif container is None or container['created'] is not True or container['removed'] is not True:
            raise CaptureError('orchestration-container-cleanup-unconfirmed')


def run(control,contract_path,expected_contract_sha,scenario,*,pipe_only=False):
    if scenario not in SCENARIOS or type(pipe_only) is not bool:raise CaptureError('orchestration-scope')
    control=path_without_links(control);private_directory(control)
    registered=contract.load(contract_path,expected_contract_sha);before=pins()
    with owner_lock(control):
        # The sole allowance is independent of output names or a later contract.
        if set(p.name for p in control.iterdir())!={'r1-supervisor.lock'}:
            raise CaptureError('orchestration-control-consumed-or-not-empty')
        admission={'schema_version':1,'mode':'offline-synthetic-only','scenario':scenario,
                   'transport':'pipe' if pipe_only else 'docker-unix','contract_sha256':expected_contract_sha,
                   'contract_source_digest':registered['source_digest'],'source_sha256':before,
                   'live_launch_authorized':False,'automatic_resume_allowed':False}
        admission_sha=write(control,'admission.json',admission)
        exclusive_file(control/'contract.json',read_private(contract_path,65536))
        registry=control/'lifecycle-registry';journal=control/'lifecycle-journal';runtime=control/'runtime'
        for folder in (registry,journal,runtime):folder.mkdir(mode=0o700)
        backend=None;operation_failed=False;cleanup_sha=None
        with tempfile.TemporaryDirectory(prefix='r1-run-ipc-') as tmp:
            try:
                with lifecycle.Lifecycle(registry,journal,expected_contract_sha,registered['source_digest']) as coordinator:
                    backend=Backend(runtime,Path(tmp),'cleanup-failure' if scenario=='cleanup-failure' else 'normal',pipe_only=pipe_only)
                    backend.prepare()
                    class Adapter:
                        def perform(self,action,op,known):
                            if scenario=='shutdown-interruption' and action=='stop_shared':
                                # Kill/reap the real synthetic broker after retirement;
                                # leave the durable shutdown intent unconfirmed.
                                reap(backend.broker)
                                raise CaptureError('synthetic-shutdown-interruption')
                            return backend.perform(action,op,known)
                    for action in lifecycle.ACTIONS:coordinator.step(action,Adapter())
            except BaseException:
                operation_failed=True
            finally:
                previous={s:signal.signal(s,signal.SIG_IGN) for s in (signal.SIGTERM,signal.SIGINT)}
                try:
                    if backend:backend.close()
                finally:
                    try:
                        # Observations survive an unconfirmed cleanup as well;
                        # this file alone is not a success receipt.
                        if backend:cleanup_sha=write(control,'cleanup.json',backend.receipt())
                    finally:
                        for s,handler in previous.items():signal.signal(s,handler)
        if backend is None:raise CaptureError('orchestration-backend-unavailable')
        cleanup=backend.receipt();cleanup_valid(cleanup,pipe_only)
        if cleanup_sha!=digest(read_private(control/'cleanup.json',65536)):
            raise CaptureError('orchestration-cleanup-observation-changed')
        state=lifecycle.inspect(registry,journal)
        if operation_failed==state['complete']:raise CaptureError('orchestration-operation-state')
        claim_raw=read_private(registry/'claim.json',4096);journal_raw=read_private(journal/'events.jsonl',lifecycle.MAX_LOG)
        intent={'schema_version':1,'admission_sha256':admission_sha,'cleanup_sha256':cleanup_sha,
                'claim_sha256':digest(claim_raw),'lifecycle_sha256':digest(journal_raw),
                'contract_sha256':expected_contract_sha,'operation_complete':state['complete']}
        intent_sha=write(control,'finalization-intent.json',intent)
        # Revalidate before preserving; failure consumes admission but earns no receipt.
        contract.load(control/'contract.json',expected_contract_sha)
        if before!=pins():raise CaptureError('orchestration-sources-changed')
        evidence=preserve.preserve(runtime/'broker/capture',runtime/'broker/session.jsonl',registry,journal,
                                  control/'contract.json',expected_contract_sha,control/'preserved')
        restored=preserve.restore(control/'preserved/evidence.zip',evidence['archive_sha256'],control/'restored')
        if restored['assessment']!=evidence['assessment']:raise CaptureError('orchestration-restore-mismatch')
        if state['complete'] and evidence['assessment']['classification']!='complete-replayed-evidence':
            raise CaptureError('orchestration-complete-evidence-missing')
        if not state['complete'] and evidence['assessment']['classification']!='quarantined-incomplete-evidence':
            raise CaptureError('orchestration-interruption-hidden')
        if before!=pins():raise CaptureError('orchestration-sources-changed')
        completion={'schema_version':1,'admission_sha256':admission_sha,'finalization_intent_sha256':intent_sha,
                    'cleanup_sha256':cleanup_sha,'archive_sha256':evidence['archive_sha256'],
                    'archive_bytes':evidence['archive_bytes'],'classification':evidence['assessment']['classification'],
                    'preservation_report_sha256':digest(read_private(control/'preserved/report.json',65536)),
                    'restore_report_sha256':digest(read_private(control/'restored/report.json',65536)),
                    'operation_complete':state['complete'],'finalization_complete':True,
                    'reconciliation_required':not state['complete'],'live_launch_authorized':False,
                    'automatic_resume_allowed':False,'full_gate_accepted':False}
        # Last publication: existence means local archive AND independent restore succeeded.
        write(control,'completion.json',completion)
        return {'admission':admission,'completion':completion,'lifecycle_state':state,'cleanup':cleanup,
                'preserved':evidence,'restored':restored,'operation_failed':operation_failed}


def inspect(control):
    """Read-only reconciliation: no locks/files created, replay, adapter or retry."""
    result={'status':'reconciliation-required','automatic_resume_allowed':False,
            'live_launch_authorized':False,'finalization_complete':False,'reconciliation_required':True}
    try:
        control=path_without_links(control);private_directory(control)
        with preserve.existing_lock(control/'r1-supervisor.lock'):
            admission,admission_sha=read(control,'admission.json')
            if (set(admission)!={'schema_version','mode','scenario','transport','contract_sha256',
                    'contract_source_digest','source_sha256','live_launch_authorized','automatic_resume_allowed'}
                    or type(admission['schema_version']) is not int or admission['schema_version']!=1
                    or admission['mode']!='offline-synthetic-only' or admission['scenario'] not in SCENARIOS
                    or admission['transport'] not in ('pipe','docker-unix')
                    or admission['source_sha256']!=pins() or admission['live_launch_authorized'] is not False
                    or admission['automatic_resume_allowed'] is not False):raise CaptureError('orchestration-admission')
            registered=contract.load(control/'contract.json',admission['contract_sha256'])
            if registered['source_digest']!=admission['contract_source_digest']:raise CaptureError('orchestration-contract-binding')
            state=lifecycle.inspect(control/'lifecycle-registry',control/'lifecycle-journal');result['lifecycle_state']=state
            intent,intent_sha=read(control,'finalization-intent.json');cleanup,cleanup_sha=read(control,'cleanup.json')
            cleanup_valid(cleanup,admission['transport']=='pipe')
            expected_intent={'schema_version':1,'admission_sha256':admission_sha,'cleanup_sha256':cleanup_sha,
                'claim_sha256':digest(read_private(control/'lifecycle-registry/claim.json',4096)),
                'lifecycle_sha256':digest(read_private(control/'lifecycle-journal/events.jsonl',lifecycle.MAX_LOG)),
                'contract_sha256':admission['contract_sha256'],'operation_complete':state['complete']}
            if canonical(intent)!=canonical(expected_intent):raise CaptureError('orchestration-intent-binding')
            completion,_=read(control,'completion.json')
            raw=read_private(control/'preserved/evidence.zip',preserve.MAX_ARCHIVE)
            members=preserve.unpack(raw);manifest=strict_json(members.pop('manifest.json'))
            if (set(manifest)!={'schema_version','kind','source_sha256','contract_sha256','members','absent','assessment'}
                    or type(manifest['schema_version']) is not int or manifest['schema_version']!=1
                    or manifest['kind']!=preserve.KIND or manifest['absent']!=sorted(set(preserve.CAPS)-set(members))
                    or manifest['assessment']['classification']!=('complete-replayed-evidence' if state['complete'] else 'quarantined-incomplete-evidence')
                    or manifest['members']!={k:{'bytes':len(v),'sha256':digest(v)} for k,v in members.items()}
                    or manifest['source_sha256']!=preserve.pins() or manifest['contract_sha256']!=admission['contract_sha256']
                    or digest(members['contract.json'])!=admission['contract_sha256']
                    or digest(members['claim.json'])!=intent['claim_sha256']
                    or digest(members['lifecycle.jsonl'])!=intent['lifecycle_sha256']):
                raise CaptureError('orchestration-archive-binding')
            saved,_=read(control/'preserved','report.json');restored,_=read(control/'restored','report.json')
            if saved['assessment']!=manifest['assessment'] or restored['assessment']!=manifest['assessment']:
                raise CaptureError('orchestration-assessment-binding')
            expected={'schema_version':1,'admission_sha256':admission_sha,'finalization_intent_sha256':intent_sha,
                'cleanup_sha256':cleanup_sha,'archive_sha256':digest(raw),'archive_bytes':len(raw),
                'classification':manifest['assessment']['classification'],
                'preservation_report_sha256':digest(read_private(control/'preserved/report.json',65536)),
                'restore_report_sha256':digest(read_private(control/'restored/report.json',65536)),
                'operation_complete':state['complete'],'finalization_complete':True,
                'reconciliation_required':not state['complete'],'live_launch_authorized':False,
                'automatic_resume_allowed':False,'full_gate_accepted':False}
            if canonical(completion)!=canonical(expected):raise CaptureError('orchestration-completion-binding')
            for key,value in members.items():
                if read_private(control/'restored'/key,preserve.CAPS[key])!=value:
                    raise CaptureError('orchestration-restored-bytes-changed')
            current=preserve.snapshot(control/'runtime/broker/capture',control/'runtime/broker/session.jsonl',
                control/'lifecycle-registry',control/'lifecycle-journal',control/'contract.json')
            if current!=members:raise CaptureError('orchestration-source-evidence-changed')
            result.update(status='finalized-evidence' if state['complete'] else 'finalized-quarantine-requires-reconciliation',
                finalization_complete=True,reconciliation_required=not state['complete'],
                archive_sha256=digest(raw),classification=completion['classification'],
                inspection_scope='stored receipt and byte bindings; no new database replay')
    except Exception:pass
    return result
