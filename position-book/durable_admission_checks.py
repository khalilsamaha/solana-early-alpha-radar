"""Disposable unsigned storage exercise, raw fixtures, no real RPC or keys."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import durable_admission as m
from pre_sign_checks import fixture,NOW
from locked_admission_checks import home_fixture


@contextmanager
def case(*,read_hook=None,collect_hook=None):
    e,p=fixture()
    with tempfile.TemporaryDirectory() as d:
        a=p['scope']['accounts'];home=home_fixture(Path(d)/'source',a['wallet'])
        c=SimpleNamespace(home=home,e=e,p=p,wallet=a['wallet'],pool=a['pool'],now=NOW+200,mono=0,reads=0,collections=0)
        with patch.object(m.timing.admission,'BASELINE',e['costInputs']['baseline']):
            deadline=m.review(e,p,c.now)['validUntilExclusiveMs']
        c.deadline=deadline
        def collect(*args,**kw):
            c.collections+=1;kw['_evidence_sink'](deepcopy(e))
            r=dict(state='controlled-cost-observation-consistent',stage='complete',networkRequests=20,requestMethods=['getGenesisHash']*20,
                   costReadiness=dict(validUntilExclusiveMs=deadline),preflight=dict(validUntilExclusiveMs=deadline),
                   binding=dict(binding=dict(validUntilExclusiveMs=deadline)))
            if collect_hook:collect_hook(c,r)
            return r
        def read(*args):
            c.reads+=1;r=deepcopy(e['costInputs']['reservations']);r.update(readStartedAtMs=c.now,observedAtMs=c.now)
            if read_hook:read_hook(c,c.reads,r)
            return r
        with patch.object(m.timing.fresh_quote,'observe',collect),patch.object(m.view,'read_locked',read),\
             patch.object(m.timing.admission,'BASELINE',e['costInputs']['baseline']),\
             patch('socket.socket',side_effect=AssertionError('network')),patch('core.signer',side_effect=AssertionError('signer')):
            c.run=lambda **kw:m.prepare(home,c.wallet,c.pool,allow_local_rehearsal=kw.get('allow',True),
                maximum_exit_attempts=2,maximum_exit_fee_lamports='10000',maximum_total_fee_lamports='30000',clock=lambda:c.now,monotonic=lambda:c.mono)
            c.status=lambda:m.status(home,c.wallet,c.pool,clock=lambda:c.now)
            c.path=m.storage(home)/m.NAME
            c.files=lambda:{str(p.relative_to(home.parent)):p.read_bytes() for p in home.parent.rglob('*') if p.is_file()}
            yield c


def empty(c):
    r=c.status();assert r['state']=='preparation-incomplete' and r['reservationRecorded'] is False,r
    with sqlite3.connect(c.path) as db:
        assert db.execute('SELECT COUNT(*) FROM admission_events').fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='rehearsal_capture'").fetchone()[0]==0


@contextmanager
def after_commit(callback):
    transaction=m.timing.admission.Journal.transaction
    fired=[False]
    @contextmanager
    def wrapped(book):
        with transaction(book):yield
        # Initialization transactions have no capture table. Inject only after
        # the atomic reservation+capture COMMIT, never before it.
        found=book.db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='rehearsal_capture'").fetchone()[0]
        if found and not fired[0]:fired[0]=True;callback()
    with patch.object(m.timing.admission.Journal,'transaction',wrapped):yield


def run():
    cases={}
    with case() as c:
        original={p.name:p.read_bytes() for p in c.home.iterdir()};r=c.run()
        assert r['state']=='unsigned-rehearsal-recorded' and r['commitOnTimeObserved'] and r['reservationRecorded'],r
        assert c.reads==2 and c.collections==1
        cases['reservation-and-private-capture-commit-together']='passed'
        with sqlite3.connect(c.path) as db:
            assert db.execute('SELECT COUNT(*) FROM admission_events').fetchone()[0]==1
            assert db.execute('SELECT COUNT(*) FROM rehearsal_capture').fetchone()[0]==1
        cases['one-reservation-event-no-signing-boundary']='passed'
        assert not (c.home.parent/(c.home.name+'-entry-handoff-v1')).exists()
        assert not r['signerCompatibleStorage'] and not r['productionReservationsCreated']
        cases['operational-admission-slot-remains-empty']='passed'
        assert original=={p.name:p.read_bytes() for p in c.home.iterdir()}
        cases['closed-source-files-unchanged']='passed'
        before=c.files();s=c.status();assert s['reservationRecorded'] and not s['commitTimingKnown'] and before==c.files(),s
        cases['read-only-recovery-replays-raw-evidence-without-writes']='passed'
        text=json.dumps(r);assert 'simulation_item' not in text and 'unsignedTransactionBase64' not in text
        cases['public-report-excludes-private-evidence']='passed'
        repeated=c.run();assert repeated['diagnosticCode']=='rehearsal-slot-occupied' and c.collections==1 and before==c.files()
        cases['repeat-prepare-preserves-slot-before-rpc']='passed'
        c.now=c.deadline+1;s=c.status();assert s['state']=='unsigned-rehearsal-expired' and s['reservationRecorded'] and c.files()==before,s
        cases['expiry-does-not-release-rehearsal-commitment']='passed'
        (c.home/'STOP').touch(mode=0o600);before=c.files();assert c.status()['state']=='unsigned-rehearsal-stopped' and before==c.files()
        cases['stop-preserves-readable-historical-reservation']='passed'
    with case() as c:
        assert c.run(allow=False)['state']=='unavailable' and c.collections==0 and not c.path.exists()
        cases['explicit-local-write-opt-in-required']='passed'
        (c.home.parent/(c.home.name+'-entry-handoff-v1')).mkdir()
        assert c.run()['state']=='unavailable' and c.collections==0
        cases['occupied-operational-slot-blocks-rehearsal']='passed'
    with case(collect_hook=lambda c,r:setattr(c,'now',c.deadline)) as c:
        assert c.run()['state']=='unavailable' and not c.path.exists()
        cases['expired-collection-does-not-create-storage']='passed'
    for mode in ('source','stop','expiry','clock','monotonic'):
        def changed(c,n,r):
            if n!=2:return
            if mode=='source':r['ledgerHeadSha256']='d'*64
            if mode=='stop':(c.home/'STOP').touch(mode=0o600)
            if mode=='expiry':c.now=c.deadline
            if mode=='clock':r['readStartedAtMs']=NOW-1
            if mode=='monotonic':c.mono=31
        with case(read_hook=changed) as c:
            assert c.run()['state']=='rehearsal-inspection-required';empty(c)
        cases['precommit-'+mode+'-rolls-back-event-and-capture']='passed'
    with case() as c,patch.object(m,'insert_capture',side_effect=OSError('private-error')):
        r=c.run();assert r['state']=='rehearsal-inspection-required' and 'private-error' not in json.dumps(r);empty(c)
        cases['storage-failure-rolls-back-and-sanitizes-error']='passed'
    with case() as c:
        with after_commit(lambda:setattr(c,'now',c.deadline)):r=c.run()
        assert r['state']=='unsigned-rehearsal-recorded-unusable' and r['reservationRecorded'] and not r['commitOnTimeObserved'],r
        assert c.status()['state']=='unsigned-rehearsal-expired'
        cases['late-commit-retains-reservation-without-on-time-claim']='passed'
    with case() as c:
        def lost():raise OSError('lost acknowledgement')
        with after_commit(lost):r=c.run()
        assert r['state']=='rehearsal-inspection-required' and r['reservationRecorded'] is None,r
        assert c.status()['reservationRecorded'];assert c.collections==1
        cases['ambiguous-commit-resolves-with-read-only-inspection']='passed'
    with case() as c:
        c.run()
        with sqlite3.connect(c.path) as db:db.execute("UPDATE rehearsal_capture SET hash='wrong'")
        before=c.files();s=c.status();assert s['state']=='rehearsal-inspection-required' and s['reservation'] is None and c.files()==before
        cases['corrupt-capture-cannot-report-valid-reservation']='passed'
    with case() as c:
        before=c.files();s=c.status();assert s['state']=='rehearsal-not-found' and c.files()==before
        cases['missing-recovery-does-not-create-storage']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',casesPassed=len(cases),cases=cases,
        mode='synthetic-offline',realNetworkRequests=0,privateKeyAccessed=False,signaturesCreated=0,transactionsSent=0,
        sourceStateChanged=False,productionReservationsCreated=False,operationalAdmissionCreated=False,
        temporaryLedgersRemoved=True,executionApproved=False,runtimeIntegrated=False)
