"""Atomic collected exit preparation and offline replay; no signer or sender.

Only the internal collector feeds this coordinator. RPC provenance is local
recorded evidence, not an external attestation or a transferable authorization.
"""
import base64
from copy import deepcopy
import json
import time

import admission_exit as exit
import admission_exit_capture as capture
from contract import digest,fields,uint,decode_wire,PROGRAM
from core import check,context_value
from recorded_capture import GENESIS

VERSION='admission-exit-collection-1'
MAX_COLLECTION=12*1024*1024


def received(item):
    check(item.get('state')=='received','exit-collection-response')
    return item['result']


def preflight_requests(c,baseline):
    ev=c['evidence'];opts=dict(encoding='base64',commitment='finalized',minContextSlot=baseline['observedSlot'])
    rows=[('getGenesisHash',[],ev['genesisBefore']),
          ('getMultipleAccounts',[[PROGRAM],opts],ev['programBootstrap'])]
    pslot=received(ev['programBootstrap'])['context']['slot']
    rows.append(('getMultipleAccounts',[[c['pool']],dict(opts,minContextSlot=pslot)],ev['poolBootstrap']))
    bslot=received(ev['poolBootstrap'])['context']['slot']
    rows.append(('getMultipleAccounts',[c['accountKeys'],dict(opts,minContextSlot=bslot)],ev['accounts']))
    slot=received(ev['accounts'])['context']['slot']
    rows.append(('getBlockTime',[slot],ev['blockTime']))
    if c['packet'] is not None:
        packet=c['packet'];opts=dict(commitment='finalized',minContextSlot=slot)
        rows.extend([('isBlockhashValid',[packet['policy']['blockhash'],opts],ev['blockhash']),
            ('getFeeForMessage',[base64.b64encode(decode_wire(packet['unsignedTransactionBase64'])[1]).decode(),opts],ev['fee'])])
    rows.append(('getGenesisHash',[],ev['genesisAfter']))
    return rows



def request_metadata(group,rows):
    check(type(group) is list and len(group)==len(rows),'exit-collection-request-metadata')
    for index,(item,(method,_,_)) in enumerate(zip(group,rows),1):
        fields(item,{'method','id','state','elapsedMs'},'exit-collection-request-metadata')
        uint(item['elapsedMs'],30000,'exit-collection-request-elapsed')
        check(type(item['id']) is int and item['id']==index and item['method']==method and
              item['state']=='received','exit-collection-request-metadata')


def review(book,evidence,collection,now,binding):
    check(len(exit.encoded(collection).encode())<=MAX_COLLECTION,'exit-collection-cap')
    fields(collection,{'initialCapture','packetBuild','requestTrace','finalGenesis','provenance'},'exit-collection-schema')
    first=collection['initialCapture'];built=collection['packetBuild'];trace=collection['requestTrace'];p=collection['provenance']
    fields(p,{'format','identity','startedAtMs','completedAtMs','evidenceSha256','initialCaptureSha256',
        'packetBuildSha256','requestTraceSha256','finalGenesisSha256','networkRequests',
        'simulationParametersSha256','validUntilExclusiveMs','durable'},'exit-collection-provenance')
    check(p['format']==capture.VERSION+'-provenance' and p['durable'] is False and
          type(p['networkRequests']) is int and p['networkRequests']==20,'exit-collection-kind')
    for k in ('startedAtMs','completedAtMs','validUntilExclusiveMs'):uint(p[k],2**53-1,'exit-collection-clock',minimum=1)
    check(p['startedAtMs']<=p['completedAtMs']<=now<p['validUntilExclusiveMs'],'exit-collection-expired')
    check(p['validUntilExclusiveMs']==min(p['startedAtMs']+10000,binding['validUntilExclusiveMs']),
          'exit-collection-deadline')
    for k,obj in (('evidenceSha256',evidence),('initialCaptureSha256',first),('packetBuildSha256',built),
                  ('requestTraceSha256',trace),('finalGenesisSha256',collection['finalGenesis'])):
        check(p[k]==digest(obj),'exit-collection-content-binding')
    # Full journal replay first; use its historical state at collection time so a
    # later STOP remains inspectable without rewriting the original provenance.
    book.read()
    row=book.db.execute('SELECT value FROM admission_events WHERE at_ms<=? ORDER BY seq DESC LIMIT 1',(p['startedAtMs'],)).fetchone()
    check(row is not None,'exit-collection-admission-history')
    state=json.loads(row['value']);check(state['state']=='signed-recorded','exit-collection-admission-history')
    record,_=exit.owner(book,now)
    check(record['recordedAtMs']<=p['startedAtMs'],'exit-collection-before-accounting')
    identity=dict(entryAccountingSha256=digest(record),admissionStateSha256=digest(state),
        policySha256=digest(book.policy),reservationSha256=digest(state),
        ledgerHeadSha256=state['ledgerHeadSha256'],cycleBindingSha256=state['cycleBindingSha256'])
    check(identity==p['identity'],'exit-collection-identity')
    check(exit.preflight._review(first,deepcopy(exit.BASELINE),now)['state']=='pinned-pool-snapshot',
          'exit-collection-initial-preflight')
    raw,_=exit.preflight.split_capture(first)
    check(raw==evidence['initialPool'] and first['packet'] is None,'exit-collection-initial-binding')
    packet=evidence['packet'];second=evidence['capture'];scope=exit.scope_for(packet['policy'])
    check(built['format']=='fresh-devnet-swap-packet-1' and built['packet']==packet and
          built['scopeSha256']==digest(scope) and built['networkRequests']==4,'exit-collection-packet-binding')
    fields(built,{'format','packet','scopeSha256','evidence','requests','networkRequests',
        'signaturesCreated','transactionsSent','signingApproved','lastValidBlockHeight','note'},'exit-collection-build-schema')
    check(type(built['networkRequests']) is int and built['signaturesCreated']==built['transactionsSent']==0 and
          built['signingApproved'] is False,'exit-collection-build-flags')
    fields(collection['finalGenesis'],{'state','result'},'exit-collection-final-genesis')
    ev=built['evidence'];fields(ev,{'genesisBefore','blockhash','fee','genesisAfter'},'exit-collection-packet-responses')
    slot,value=context_value(ev['blockhash'],received(first['evidence']['accounts'])['context']['slot'])
    check(value['blockhash']==packet['policy']['blockhash'] and
          value['lastValidBlockHeight']==built['lastValidBlockHeight'],'exit-collection-blockhash')
    uint(value['lastValidBlockHeight'],2**64-1,'exit-collection-height',minimum=1)
    _,fee=context_value(ev['fee'],slot)
    check(type(fee) is int and fee>0 and packet['feeAssertion']['lamports']==str(fee) and
          packet['feeAssertion']['observedAtMs']==ev['fee']['receivedAtMs'],'exit-collection-message-fee')
    check(packet['policy']['expiresAtMs']==packet['policy']['issuedAtMs']+15000,'exit-collection-packet-expiry')
    message=base64.b64encode(decode_wire(packet['unsignedTransactionBase64'])[1]).decode()
    packet_rows=[('getGenesisHash',[],ev['genesisBefore']),
        ('getLatestBlockhash',[dict(commitment='finalized')],ev['blockhash']),
        ('getFeeForMessage',[message,dict(commitment='finalized',minContextSlot=slot)],ev['fee']),
        ('getGenesisHash',[],ev['genesisAfter'])]
    for group in (first['evidence'],ev,second['evidence']):
        for key in ('genesisBefore','genesisAfter'):
            check(received(group[key])==GENESIS['devnet'],'exit-collection-cluster')
    check(received(collection['finalGenesis'])==GENESIS['devnet'],'exit-collection-cluster')
    params=exit.unsigned_simulation.parameters(packet,second)
    check(p['simulationParametersSha256']==digest(params),'exit-collection-simulation-parameters')
    initial_rows=preflight_requests(first,exit.BASELINE);account_rows=preflight_requests(second,exit.BASELINE)
    for group,expected in ((first,initial_rows),(built,packet_rows),(second,account_rows)):
        request_metadata(group['requests'],expected)
    check(type(first['rpcRequestsAttempted']) is int and first['rpcRequestsAttempted']==6 and
          type(second['rpcRequestsAttempted']) is int and second['rpcRequestsAttempted']==8,'exit-collection-request-count')
    rows=initial_rows+packet_rows+account_rows+[
        ('simulateTransaction',params,dict(evidence['simulationItem'],receivedAtMs=evidence['simulationReceivedAtMs'])),
        ('getGenesisHash',[],dict(collection['finalGenesis'],receivedAtMs=evidence['completedAtMs']))]
    check(type(trace) is list and len(trace)==20,'exit-collection-trace')
    prior=p['startedAtMs']
    for item,(method,params,response) in zip(trace,rows):
        fields(item,{'method','parametersSha256','requestedAtMs'},'exit-collection-request')
        stamp=item['requestedAtMs'];end=response['receivedAtMs'];received(response)
        uint(stamp,2**53-1,'exit-collection-clock',minimum=1);uint(end,2**53-1,'exit-collection-clock',minimum=1)
        check(item['method']==method and item['parametersSha256']==digest(params),'exit-collection-request-binding')
        check(prior<=stamp<=end<=p['completedAtMs'],'exit-collection-request-clock');prior=end
    check(p['startedAtMs']<=first['startedAtMs']<=trace[0]['requestedAtMs'] and
          first['evidence']['genesisAfter']['receivedAtMs']<=first['finishedAtMs']<=packet['policy']['issuedAtMs']<=trace[6]['requestedAtMs'] and
          ev['genesisAfter']['receivedAtMs']<=second['startedAtMs']<=trace[10]['requestedAtMs'] and
          second['evidence']['genesisAfter']['receivedAtMs']<=second['finishedAtMs']<=evidence['simulationStartedAtMs']<=trace[18]['requestedAtMs'],
          'exit-collection-stage-clock')
    return dict(binding,collectionSha256=digest(collection),validUntilExclusiveMs=p['validUntilExclusiveMs'])


@exit.view.cycles.binding.operation
def collect_and_prepare(home,wallet,pool,*,opener=None,clock=exit.view.now,monotonic=time.monotonic,
                        _observation_sink=None):
    """Internal coordinator: no report importer, no CLI runtime or signing path."""
    check(_observation_sink is None or callable(_observation_sink),'exit-collection-observation-sink')
    existing=exit.status(home,wallet,pool,clock=clock)
    if existing['recorded']:return dict(existing,collectionRequestsThisRun=0)
    items=[]
    observed=capture.collect(home,wallet,pool,opener=opener,clock=clock,monotonic=monotonic,_evidence_sink=items.append)
    if _observation_sink is not None:_observation_sink(deepcopy(observed))
    if observed['state']!='exit-evidence-collected-research-only':return observed
    check(len(items)==1,'exit-collection-handoff')
    envelope=items[0];evidence=envelope.pop('evidence')
    # The collector has released its read-only connections. prepare reacquires
    # the lock and independently rechecks identity, STOP, provenance and expiry.
    result=exit.prepare(home,wallet,pool,evidence,clock=clock,_collection=envelope)
    return dict(result,collectionRequestsThisRun=observed['networkRequests'])
