"""Atomic persistence checks over real collectors and synthetic, bounded RPC."""
from copy import deepcopy
import json
import sqlite3
from unittest.mock import patch

import admission_exit_collection as m
import admission_exit_capture_checks as fixture
from admission_submission_checks import case,refuses
from entry_accounting_checks import collect,apply


def collected(c):
    items=[];r,_=fixture.capture(c,sink=items.append)
    assert r['state']=='exit-evidence-collected-research-only'
    c.now=r['provenance']['completedAtMs']+1
    envelope=items[0];e=envelope.pop('evidence');_,_,baseline=fixture.setup(c)
    return e,envelope,baseline


def prepare(c,e,proof,baseline):
    with patch.object(m.exit,'BASELINE',baseline),patch.object(m.exit.view,'read_locked',return_value=c.e['costInputs']['reservations']):
        return m.exit.prepare(c.home,c.wallet,c.pool,e,clock=lambda:c.now,_collection=proof)


def status(c,b):
    with patch.object(m.exit,'BASELINE',b):return m.exit.status(c.home,c.wallet,c.pool,clock=lambda:c.now)


def rehash(proof,e):
    p=proof['provenance']
    for k,v in (('evidenceSha256',e),('initialCaptureSha256',proof['initialCapture']),
                ('packetBuildSha256',proof['packetBuild']),('requestTraceSha256',proof['requestTrace']),
                ('finalGenesisSha256',proof['finalGenesis'])):p[k]=m.digest(v)


def run():
    cases={}
    with case() as c:
        collect(c);entry=apply(c);e,p,b=collected(c)
        source={x.name:x.read_bytes() for x in c.home.iterdir()}
        result=prepare(c,e,p,b)
        assert result['collectionRecorded'] and result['collectionProvenanceReplayed'] and result['createdThisRun']
        assert result['binding']['quantityAtomic']=='98' and result['binding']['feeCommitmentRemainingLamports']=='20999'
        assert result['binding']['validUntilExclusiveMs']==p['provenance']['validUntilExclusiveMs']
        cases['raw-preparation-and-collection-committed-as-one-record']='passed'
        old=c.path.read_bytes();reopened=status(c,b)
        assert reopened['recordSha256']==result['recordSha256'] and c.path.read_bytes()==old
        assert not prepare(c,e,p,b)['createdThisRun'] and c.path.read_bytes()==old
        cases['read-only-reopen-and-idempotent-retry-preserve-bytes']='passed'
        assert source=={x.name:x.read_bytes() for x in c.home.iterdir()} and apply(c)['recordSha256']==entry['recordSha256']
        assert not result['reservationReleased'] and not result['signingApproved'] and not result['validForSubmission']
        assert 'unsignedTransactionBase64' not in json.dumps(result)
        cases['source-accounting-fees-and-public-boundaries-preserved']='passed'
        c.now+=30000;assert status(c,b)['state']=='exit-preparation-expired'
        assert prepare(c,e,p,b)['state']=='exit-preparation-expired' and c.path.read_bytes()==old
        cases['expired-replay-does-not-refresh-or-rewrite']='passed'
        book=c.book()
        try:book.stop()
        finally:book.close()
        stopped=c.path.read_bytes();assert status(c,b)['state']=='exit-preparation-stopped'
        assert c.path.read_bytes()==stopped
        cases['later-durable-stop-keeps-historical-provenance-readable']='passed'
    mutations={
        'wrong-final-cluster':lambda e,p:p['finalGenesis'].update(result='wrong'),
        'wrong-initial-cluster':lambda e,p:p['initialCapture']['evidence']['genesisBefore'].update(result='wrong'),
        'wrong-packet-cluster':lambda e,p:p['packetBuild']['evidence']['genesisAfter'].update(result='wrong'),
        'changed-request-parameters':lambda e,p:p['requestTrace'][8].update(parametersSha256='0'*64),
        'changed-request-method':lambda e,p:p['requestTrace'][18].update(method='sendTransaction'),
        'request-clock-regression':lambda e,p:p['requestTrace'][10].update(requestedAtMs=1),
        'wrong-admission-identity':lambda e,p:p['provenance']['identity'].update(admissionStateSha256='0'*64),
        'deadline-extension':lambda e,p:p['provenance'].update(validUntilExclusiveMs=p['provenance']['validUntilExclusiveMs']+1),
        'missing-provenance':lambda e,p:p.pop('provenance'),
        'packet-fee-contradiction':lambda e,p:p['packetBuild']['evidence']['fee']['result'].update(value=5002),
        'packet-blockhash-contradiction':lambda e,p:p['packetBuild']['evidence']['blockhash']['result']['value'].update(blockhash=c.wallet),
        'simulation-parameters-mismatch':lambda e,p:p['provenance'].update(simulationParametersSha256='0'*64),
    }
    for name,mutate in mutations.items():
        with case() as c:
            collect(c);apply(c);e,p,b=collected(c);mutate(e,p)
            if 'provenance' in p:rehash(p,e)
            old=c.path.read_bytes()
            try:prepare(c,e,p,b)
            except (ValueError,KeyError):pass
            else:raise AssertionError(name)
            assert c.path.read_bytes()==old
            cases[name+'-rejected-even-with-updated-hashes']='passed'
    for mode in ('storage-failure','stop-before-commit','expiry-before-commit'):
        with case() as c:
            collect(c);apply(c);e,p,b=collected(c);old=c.path.read_bytes();writer=m.exit.write_record
            def fault(book,record):
                writer(book,record)
                if mode=='storage-failure':raise OSError('synthetic storage failure')
                if mode=='stop-before-commit':(c.home/'STOP').touch(mode=0o600)
                if mode=='expiry-before-commit':c.now+=10000
            with patch.object(m.exit,'write_record',side_effect=fault):refuses(lambda:prepare(c,e,p,b))
            assert c.path.read_bytes()==old
            cases[mode+'-rolls-back-entire-record']='passed'
    with case() as c:
        collect(c);apply(c);e,p,b=collected(c)
        fixture.prepare(c,e,b);old=c.path.read_bytes()
        refuses(lambda:prepare(c,e,p,b));assert c.path.read_bytes()==old
        assert not status(c,b)['collectionRecorded']
        cases['legacy-raw-preparation-cannot-be-upgraded']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',
        casesPassed=len(cases),cases=cases,networkRequests=0,signaturesCreated=0,transactionsSent=0,
        privateKeyAccessed=False,temporaryLedgersRemoved=True,productionLedgerUpdated=False,
        atomicCollectionAndPreparation=True,reservationReleased=False,allocationTransferred=False,
        executionApproved=False,runtimeIntegrated=False,nextCycleAuthorized=False)
