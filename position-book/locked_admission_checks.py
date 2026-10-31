"""Disposable locks/ledgers and public signature fixture; no key or RPC access."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import locked_admission as bridge
import pre_sign_admission as admission
from pre_sign_checks import fixture as raw_fixture, NOW, reject
from paired_checks import edit, simulation_response
from wire import decode_wire
from cpmm_quote import derive


def fixture(signed_fixture=None):
    e,p=raw_fixture()
    signed=deepcopy(signed_fixture) if signed_fixture is not None else json.loads(Path(__file__).with_name('admission-signed-fixture.json').read_text())
    wallet=signed['wallet'];a=e['costInputs'];c=a['capture']
    for scope in (e['scope'], e['entryScope'], p['scope'], a['packet']['policy']):
        scope['accounts']['wallet']=wallet
    unsigned=signed['unsignedTransactionBase64']
    _,message,keys,_,_=decode_wire(unsigned)
    a['packet']['unsignedTransactionBase64']=unsigned
    a['packet']['feeAssertion']['messageSha256']=hashlib.sha256(message).hexdigest()
    c['messageSha256']=hashlib.sha256(message).hexdigest()
    c['accountKeys'][8]=wallet
    edit(c,9,32,keys[0]);edit(c,10,32,keys[0])
    a['reservations']['wallet']=wallet
    a['price']=derive(e['initialPool'],e['scope'],slippage_bps=100,now_ms=NOW+200)
    response=simulation_response(c,a['price']['quote']['outAmount'])
    response['value']['failed']=False;response['value'].pop('err')
    a['simulation_item']['result']=response
    return e,p,signed


def home_fixture(path,wallet):
    path.mkdir(mode=0o700)
    (path/'session.lock').touch(mode=0o600)
    meta=dict(format='devnet-wallet-1',network='devnet',purpose='fixed-self-transfer-rehearsal',wallet=wallet)
    (path/'wallet.json').write_text(json.dumps(meta));(path/'wallet.json').chmod(0o600)
    return path


def run():
    e,p,signed=fixture();cases={};wallet=p['scope']['accounts']['wallet'];pool=p['scope']['accounts']['pool']
    with tempfile.TemporaryDirectory() as tmp, patch.object(admission,'BASELINE',e['costInputs']['baseline']):
        root=Path(tmp);home=home_fixture(root/'source',wallet);stamp=[NOW+200]
        snapshot=deepcopy(e['costInputs']['reservations'])
        snapshot.update(readStartedAtMs=stamp[0],observedAtMs=stamp[0])
        b=admission.Admission(root/'check.admission.sqlite',p,lambda:stamp[0])
        try:
            with patch.object(bridge.view,'read_locked',return_value=snapshot):
                r=bridge.prepare(home,wallet,pool,b,e,clock=lambda:stamp[0])
                assert r['admission']['state']=='signing-unknown' and r['sourceReservationProvenanceVerified']
                cases['locked-two-read-admission']='passed'
                reject(lambda:bridge.prepare(home,wallet,pool,b,e,clock=lambda:stamp[0]))
                cases['no-second-boundary']='passed'
            b.close();b=admission.Admission(root/'check.admission.sqlite',clock=lambda:stamp[0])
            assert b.status()['state']=='signing-unknown';cases['lost-ack-holds-on-reopen']='passed'
            stamp[0]+=20000
            r=b.record_signed(signed['signedTransactionBase64'])
            assert r['state']=='signed-recorded' and r['reservation']['reservedFeeLamports']=='26000'
            cases['expired-exact-ack-recorded-without-send']='passed'
            assert signed['signedTransactionBase64'] not in json.dumps(r)
            cases['signed-wire-private']='passed'
            assert b.record_signed(signed['signedTransactionBase64'])==r
            cases['duplicate-ack-idempotent']='passed'
            r=b.stop();r=b.record_signed(signed['signedTransactionBase64']);assert r['state']=='stopped'
            cases['stop-retains-signed-commitment']='passed'
            r=b.record_signed(signed['otherSignedTransactionBase64']);assert r['state']=='quarantined'
            assert r['reservation']['reservedFeeLamports']=='26000'
            cases['valid-signature-wrong-message-quarantined']='passed'
            assert b.stop()==r and b.record_signed(signed['signedTransactionBase64'])==r
            cases['quarantine-cannot-be-cleared-by-stop-or-ack']='passed'
        finally:b.close()
        stamp[0]=NOW+200
        b=admission.Admission(root/'before.admission.sqlite',p,lambda:stamp[0])
        try:
            b.reserve(e);old=b.status()
            reject(lambda:b.record_signed(signed['signedTransactionBase64']));assert old==b.status()
            cases['ack-requires-durable-boundary']='passed'
            b.mark_signing_boundary(e)
            wire=bytearray(base64.b64decode(signed['signedTransactionBase64']));wire[1]^=1
            assert b.record_signed(base64.b64encode(wire).decode())['state']=='quarantined'
            cases['bad-signature-quarantined']='passed'
        finally:b.close()
        for mode in ('before','after','expired','stop','clock'):
            b=admission.Admission(root/(mode+'-source.admission.sqlite'),p,lambda:stamp[0])
            calls=[0];stamp[0]=NOW+200
            def read(*args):
                calls[0]+=1;v=deepcopy(snapshot)
                if mode=='before' or (mode=='after' and calls[0]==2):v['ledgerHeadSha256']='c'*64
                if mode=='expired' and calls[0]==2:stamp[0]=NOW+20000
                if mode=='stop' and calls[0]==2:(home/'STOP').touch(mode=0o600)
                if mode=='clock' and calls[0]==2:v['readStartedAtMs']=NOW+199
                return v
            try:
                with patch.object(bridge.view,'read_locked',side_effect=read):
                    reject(lambda:bridge.prepare(home,wallet,pool,b,e,clock=lambda:stamp[0]))
                assert b.status()['state']==('empty' if mode=='before' else 'reserved')
                cases['source-'+mode+'-blocks-boundary']='passed'
            finally:
                b.close();(home/'STOP').unlink(missing_ok=True)
        stamp[0]=NOW+200
        b=admission.Admission(root/'busy.admission.sqlite',p,lambda:stamp[0])
        try:
            with bridge.view.cycles.c.source_lock(home,wallet):
                try:bridge.prepare(home,wallet,pool,b,e,clock=lambda:stamp[0])
                except BlockingIOError:pass
                else:raise AssertionError('lock contention accepted')
            assert b.status()['state']=='empty';cases['real-lock-contention-blocked']='passed'
        finally:b.close()
    return dict(format=bridge.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',
                casesPassed=len(cases),cases=cases,temporaryLedgersRemoved=True,
                sourceReader='synthetic-fixture; real journal replay tested separately',**admission.FLAGS)
