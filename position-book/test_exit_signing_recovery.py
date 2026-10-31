"""Full historical-source restore retains unknown and signed exit handoffs."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import admission_exit as m
import admission_recovery as recovery
import exit_signing_handoff as signing
import test_admission_exit_recovery as original
from test_admission_exit_recovery import delayed
from contract import digest


class SigningRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        unlink=Path.unlink;keys={}
        def capture_key(path,*args,**kw):
            if path.name=='signer.pk8' and path.exists():
                meta=json.loads((path.parent/'wallet.json').read_text());keys[meta['wallet']]=path.read_bytes()
            return unlink(path,*args,**kw)
        with patch.object(Path,'unlink',capture_key):original.EndToEndExitTests.setUpClass.__func__(cls)
        cls.ephemeral_exit_key=keys[cls.wallet]
    @classmethod
    def tearDownClass(cls):
        cls.ephemeral_exit_key=None;original.EndToEndExitTests.tearDownClass.__func__(cls)
    setUp=original.EndToEndExitTests.setUp
    tearDown=original.EndToEndExitTests.tearDown
    clock=original.EndToEndExitTests.clock
    submit=original.EndToEndExitTests.submit
    collect=original.EndToEndExitTests.collect
    settle=original.EndToEndExitTests.settle
    capture=original.EndToEndExitTests.capture
    verify=original.EndToEndExitTests.verify
    source_bytes=original.EndToEndExitTests.source_bytes
    edit_db=original.EndToEndExitTests.edit_db

    def exercise(self,mode):
        import admission_exit_collection as collected
        import admission_exit_capture_checks as fixtures
        self.collect();accounting=self.settle()['accounting'];self.stamp+=30000
        e=delayed(self.e['costInputs']['capture'],accounting,self.stamp)
        raw=e['initialPool'];first=deepcopy(e['capture'])
        first.update(packet=None,selection='explicit-pool',accountKeys=raw['accountKeys']+[first['accountKeys'][-1]])
        programdata=deepcopy(first['evidence']['accounts']['result']['value'][-1])
        first['evidence']['accounts']=deepcopy(raw['evidence']['accounts'])
        first['evidence']['accounts']['result']['value'].append(programdata)
        first['evidence']['poolBootstrap']=deepcopy(raw['evidence']['bootstrap'])
        first['evidence']['programBootstrap']['result']['context']['slot']=first['evidence']['poolBootstrap']['result']['context']['slot']
        for name in ('genesisBefore','genesisAfter','blockTime'):
            first['evidence'][name]=deepcopy(raw['evidence'][name])
        first['evidence']['blockhash']={'state':'not-requested'}
        first['evidence']['fee']={'state':'not-requested'}
        baseline=deepcopy(self.e['costInputs']['baseline'])
        baseline.update(kind='observed-devnet-deployment',observedAtMs=0)
        clock=fixtures.Clock();clock.at=self.stamp
        rpc=fixtures.Opener(first,e)
        with patch.object(m,'BASELINE',baseline):
            prepared=collected.collect_and_prepare(self.home,self.wallet,self.pool,opener=rpc,clock=clock,monotonic=lambda:0)
            self.assertEqual(prepared['state'],'exit-prepared-research-only',prepared)
            self.assertTrue(prepared['collectionRecorded']);self.assertEqual(len(rpc.calls),20)
            self.stamp=clock.at+1
            def adapter(request):
                if mode=='unknown':raise TimeoutError('synthetic reply loss')
                message=base64.b64decode(request['packet']['unsignedTransactionBase64'])[65:]
                js="const c=require('node:crypto'),fs=require('node:fs');const r=JSON.parse(fs.readFileSync(0));const k=c.createPrivateKey({key:Buffer.from(r.key,'base64'),format:'der',type:'pkcs8'});const m=Buffer.from(r.message,'base64');process.stdout.write(Buffer.concat([Buffer.from([1]),c.sign(null,m,k),m]).toString('base64'));"
                result=subprocess.run(['node','-e',js],input=json.dumps(dict(key=base64.b64encode(self.ephemeral_exit_key).decode(),message=base64.b64encode(message).decode())),capture_output=True,text=True,check=True)
                return result.stdout
            if mode=='unknown':
                with self.assertRaises(TimeoutError):signing.dispatch(self.home,self.wallet,self.pool,signer_adapter=adapter,clock=self.clock)
            else:
                result=signing.dispatch(self.home,self.wallet,self.pool,signer_adapter=adapter,clock=self.clock)
                self.assertEqual(result['state'],'exit-signed-recorded')
            self.stamp+=30000;before=self.source_bytes();self.capture();self.verify()
            self.assertEqual(before,self.source_bytes())
            manifest=json.loads((self.snapshot/recovery.MANIFEST).read_text())
            expected='exit-signing-unknown' if mode=='unknown' else 'exit-signed-recorded'
            self.assertEqual(manifest['projection']['exitSigningState'],expected)
            # Rehashing every container cannot hide a changed request quantity.
            path=self.snapshot/recovery.SIBLING/'entry.admission.sqlite'
            def corrupt(db):
                rows=db.execute('SELECT seq,at_ms,value FROM admission_exit_signing ORDER BY seq').fetchall();previous=''
                for seq,at,raw in rows:
                    v=json.loads(raw)
                    if seq==1:
                        v['request']['quantityAtomic']='1';v['requestSha256']=digest(v['request'])
                    h=digest(dict(seq=seq,atMs=at,value=v,previousHash=previous))
                    db.execute('UPDATE admission_exit_signing SET value=?,previous_hash=?,hash=? WHERE seq=?',(m.encoded(v),previous,h,seq));previous=h
            self.edit_db(corrupt,path)
            manifest['inventories']=recovery.inventories(self.snapshot/recovery.SOURCE,self.snapshot/recovery.SIBLING)
            (self.snapshot/recovery.MANIFEST).write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'exit-signing-request-binding'):self.verify()

    def test_unknown_handoff_isolated_restore(self):self.exercise('unknown')
    def test_signed_handoff_isolated_restore(self):self.exercise('signed')


if __name__=='__main__':unittest.main()
