"""Offline replacement-to-transport exercise with disposable keys and synthetic RPC."""
from copy import deepcopy
from pathlib import Path
import tempfile
import json
import subprocess
import time
from types import SimpleNamespace
from unittest.mock import patch
import fresh_exit as m
from core import check
from contract import digest
from lifecycle_rehearsal import exit_inputs,leg
from unsigned_exit_replacement_checks import case,rows

VERSION='replacement-exit-integration-1'


def fault_checks():
    cases={}
    for kind in ('stop','wrong-identity','marker','write-failure','budget','lost-signer','deadline'):
        with case() as c:
            signs=[];mono=[0];write=m.replacement.write_record
            def adapter(root,request):
                signs.append(request)
                raise TimeoutError('private synthetic signer response')
            if kind=='stop':(c.home/'STOP').touch(mode=0o600)
            if kind=='wrong-identity':c.expected='0'*64
            if kind=='marker':(c.path.parent/m.backend.ATTEMPT).touch(mode=0o600)
            def hook(book,envelope):
                write(book,envelope)
                if kind=='write-failure':raise OSError('private synthetic storage')
                if kind=='budget':mono[0]=30
            def collector_hook(n,q,o):
                if kind=='deadline' and n==20:c.timer.at+=10000
            c.rpc.hook=collector_hook
            before=rows(c,'admission_exit_preparation')
            with patch.object(m.replacement,'write_record',hook):
                r=m._run(c.home,c.wallet,c.pool,signer_adapter=adapter,
                    _replacement_expected=c.expected,collection_opener=c.rpc,
                    clock=c.clock,monotonic=lambda:mono[0])
            check(r['sendRequestsThisRun']==0 and r['senderRequests']==0,'fault-send')
            check(len(signs)==(1 if kind=='lost-signer' else 0),'fault-sign')
            check(r['collectionRequests']==(0 if kind in ('stop','wrong-identity','marker') else 20),'fault-count')
            check(rows(c,'admission_exit_preparation')==before,'fault-original')
            if kind in ('budget','lost-signer'):
                again=m._run(c.home,c.wallet,c.pool,signer_adapter=adapter,
                    _replacement_expected=c.expected,clock=c.clock,monotonic=lambda:0)
                check(again['networkRequests']==0 and len(signs)==(kind=='lost-signer'),'fault-repeat')
            if kind=='lost-signer':
                check(r['privateKeyAccessed'] is None and r['signaturesCreated'] is None,'fault-unknown')
            cases[kind+'-preserves-one-attempt-boundaries']='passed'
    with patch.object(m.view.cycles.c,'source_lock',side_effect=AssertionError('scope accessed')):
        for name in ('allow_unsigned_replacement','allow_private_key_signing','allow_devnet_submit'):
            for value in (False,1,'yes'):
                opts=dict(allow_unsigned_replacement=True,allow_private_key_signing=True,allow_devnet_submit=True)
                opts[name]=value
                try:m.replace_sign_submit('/missing','w','p',expected_preparation_sha256='a'*64,**opts)
                except ValueError:pass
                else:raise AssertionError('opt-in accepted')
        try:m.prepare_sign_submit('/missing','w','p',allow_private_key_signing=True,
            allow_devnet_submit=True,_replacement_expected='a'*64)
        except ValueError:pass
        else:raise AssertionError('ordinary wrapper accepted replacement')
    cases['three-exact-opt-ins-and-no-ordinary-wrapper-bypass']='passed'
    return cases


def connected(fixture,report):
    from admission_exit_capture_checks import Opener
    from exit_submission_checks import FakeRpc
    from preflight_checks import fake_key
    f=fixture;clock=m.view.now
    f.collect();accounting=f.settle()['accounting']
    baseline=deepcopy(f.e['costInputs']['baseline']);baseline.update(kind='observed-devnet-deployment',observedAtMs=0)
    with patch.object(m.collection.exit,'BASELINE',baseline):
        first,e=exit_inputs(f.e,accounting,clock())
        old=m.collection.collect_and_prepare(f.home,f.wallet,f.pool,opener=Opener(first,e),clock=clock)
        check(old.get('createdThisRun') is True,'original-not-prepared')
        # Let actual wall time expire the synthetic original. Never move the real
        # signer's clock or widen the ten-second collection window to make a pass.
        time.sleep(max(0,(old['binding']['validUntilExclusiveMs']-clock())/1000)+0.01)
        f.stamp=clock()
        b=m.submission.transport._open(f.home,f.wallet,f.pool,clock)
        try:
            original=list(b.db.execute('SELECT * FROM admission_exit_preparation'))
            entry=list(b.db.execute('SELECT * FROM admission_entry_accounting'))
        finally:b.close()
        source={p.name:p.read_bytes() for p in f.home.iterdir() if p.is_file()}
        first,e=exit_inputs(f.e,accounting,clock());rpc=Opener(first,e)
        rpc.rows[7]['value']['blockhash']=fake_key('replacement-connected-blockhash')
        key=f.home/'signer.pk8';key.write_bytes(f.ephemeral_exit_key);key.chmod(0o600)
        transports=[]
        class Lazy:
            def open(self,request,timeout=None):
                if not transports:
                    book=m.submission.transport._open(f.home,f.wallet,f.pool,clock)
                    try:
                        state=m.submission.ExitSubmission(book).signing()
                        current=m.collection.exit.saved(book,clock())
                        check(state['request']['preparationSha256']==digest(current) and
                              state['request']['preparationSha256']!=old['recordSha256'],'replacement-signing-identity')
                        c=SimpleNamespace(exit_state=state,exit_wire=state['signed']['signedWireBase64'],path=book.j.path,signed={})
                    finally:book.close()
                    transports.append(FakeRpc(c,lost=True))
                return transports[0].open(request,timeout)
        start=time.monotonic()
        r=m.replace_sign_submit(f.home,f.wallet,f.pool,expected_preparation_sha256=old['recordSha256'],
            allow_unsigned_replacement=True,allow_private_key_signing=True,allow_devnet_submit=True,
            collection_opener=rpc,submission_opener=Lazy(),clock=clock)
        report['integrationElapsedMs']=round((time.monotonic()-start)*1000,3)
        report['integrationStage']=r['stage'];report['integrationDiagnostic']=r['diagnosticCode']
        report['collectionRequests']=r['collectionRequests'];report['senderRequests']=r['senderRequests']
        report['exit']=leg(r)
        check(r['privateKeyAccessed'] is True and r['originalDeadlineCheckedBeforeSend'],'replacement-signing-evidence')
        report['cases']['actual-isolated-signer-and-one-lost-response-send']='passed'
        check(r['preparation']['originalPreparationSha256']==old['recordSha256'],'replacement-original-identity')
        b=m.submission.transport._open(f.home,f.wallet,f.pool,clock)
        try:
            check(list(b.db.execute('SELECT * FROM admission_exit_preparation'))==original and
                  list(b.db.execute('SELECT * FROM admission_entry_accounting'))==entry,'original-records-mutated')
            data=dict(policy=json.loads(b.db.execute('SELECT value FROM admission_policy').fetchone()[0]),
                admissionRows=[dict(x) for x in b.db.execute('SELECT * FROM admission_events ORDER BY seq')],
                signingRows=[dict(b.db.execute('SELECT * FROM admission_exit_signing ORDER BY seq LIMIT 1').fetchone())],
                preparationRow=dict(original[0]),accountingRow=dict(entry[0]),
                replacementRow=dict(b.db.execute('SELECT * FROM admission_exit_replacement').fetchone()))
            boundary=json.loads(data['signingRows'][0]['value'])
            contract_input=dict(data=data,metadata=json.loads((f.home/'wallet.json').read_text()),
                pair=json.loads((f.home/'controlled-pool-v1'/'plan.json').read_text())['pairAccounts'],
                requestedHash=boundary['requestSha256'],now=data['signingRows'][0]['at_ms'])
        finally:b.close()
        key.unlink()
        contract=subprocess.run(['node',str(Path(__file__).with_name('replacement_exit_contract_checks.mjs'))],
            input=json.dumps(contract_input),capture_output=True,text=True,timeout=10,check=True)
        result=json.loads(contract.stdout);check(result['casesPassed']==10,'independent-contract-cases')
        report['independentContractCases']=result['cases']
        report['cases']['independent-signer-rejects-rehashed-lineage-and-ownership-changes']='passed'
        check({p.name:p.read_bytes() for p in f.home.iterdir() if p.is_file()}==source,'source-mutated')
        report['cases']['original-source-preparation-and-entry-accounting-preserved']='passed'
        with patch.object(m.backend,'_invoke',side_effect=AssertionError('second signer')):
            again=m.replace_sign_submit(f.home,f.wallet,f.pool,expected_preparation_sha256=old['recordSha256'],
                allow_unsigned_replacement=True,allow_private_key_signing=True,allow_devnet_submit=True,clock=clock)
            check(again['networkRequests']==again['signerInvocationAttempts']==0,'repeat-attempt')
            (f.home/'STOP').touch(mode=0o600)
            recovery=m.recover(f.home,f.wallet,f.pool,opener=transports[0],clock=lambda:clock()+30000)
        check(recovery['state']=='exit-finalized-evidence' and recovery['sendRequestsThisRun']==0 and
              not recovery['reservationReleased'] and not recovery['resumesExit'],'recovery-not-observation')
        check(sum(x['method']=='sendTransaction' for x in transports[0].requests)==1,'repeat-send')
        report['cases']['repeat-refused-before-collection-keyless-stopped-recovery-never-resends']='passed'
        report['recovery']=dict(state=recovery['state'],sendRequests=0,reservationReleased=False)


def run():
    import test_fresh_exit as fixture_module
    class Fixture(fixture_module.ActualBackendTests):pass
    report=dict(format=VERSION,state='review-required',cases=fault_checks(),casesPassed=0,
        mode='synthetic-offline',realNetworkRequests=0,productionWalletAccessed=False,
        disposableTestKeySigning=True,transactionsSent=0,productionLedgerUpdated=False,
        runtimeIntegrated=False,executionApproved=False,automaticRetryAllowed=False,
        integrationElapsedMs=None,integrationStage=None,integrationDiagnostic=None,
        limitations=['Synthetic RPC and disposable keys only; no real network latency or user position test.',
                    'The original ten-second freshness and thirty-second shared budget are unchanged.',
                    'A returned quote or finalized synthetic receipt is not evidence of profitability.'])
    with tempfile.TemporaryDirectory(prefix='radar-replacement-integration-') as owned:
        with patch.object(tempfile,'tempdir',owned),patch('socket.socket',side_effect=AssertionError('real network')):
            instance=None;started=False;setup=False
            try:
                started=True;Fixture.setUpClass();instance=Fixture();setup=True;instance.setUp()
                check(instance.home.resolve().is_relative_to(Path(owned).resolve()),'temporary-scope')
                connected(instance,report);report['state']='offline-integration-passed'
            except Exception:
                report['diagnosticCode']='connected-rehearsal-incomplete'
            finally:
                if setup:instance.tearDown()
                if started:Fixture.tearDownClass()
                Fixture.ephemeral_exit_key=None
    report['temporaryLedgersRemoved']=not Path(owned).exists()
    report['casesPassed']=len(report['cases'])
    return report
