import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import experiment as ex
from audit import digest, publish, PROTOCOL
from model import freeze, seal
from test_model import training

class ExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.reg, cls.now = training()
        cls.model = freeze(cls.data, cls.reg, cls.now)
        cls.sealed = seal(cls.model)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.directory=self.root/'experiment'; self.source=self.root/'source.gz'
        publish(self.source,self.sealed)
        pin=patch.object(ex,'ARTIFACT_SHA256',self.sealed['artifactSha256']); pin.start(); self.addCleanup(pin.stop)

    def test_install_is_private_and_repeat_does_not_reset_start_or_model(self):
        before=self.source.read_bytes()
        first=ex.install(self.source,self.directory,self.now+1000)
        files={p.name:p.read_bytes() for p in self.directory.iterdir()}
        again=ex.install(self.source,self.directory,self.now+100000)
        self.assertEqual(first,again)
        self.assertEqual(files,{p.name:p.read_bytes() for p in self.directory.iterdir()})
        self.assertEqual(before,self.source.read_bytes())
        self.assertEqual(self.directory.stat().st_mode & 0o777,0o700)
        self.assertTrue(all(p.stat().st_mode & 0o777==0o600 for p in self.directory.iterdir()))
        self.assertEqual(first['registration']['testNotBeforeAt'],self.now+301000)
        self.assertNotIn('coefficients',json.dumps(first))
        self.assertNotIn('seenTrainingMints',json.dumps(first))

    def test_wrong_artifact_even_resealed_refused(self):
        bad=copy.deepcopy(self.model); bad['frozenAt']+=1
        other=self.root/'other.gz'; publish(other,seal(bad))
        with self.assertRaisesRegex(ValueError,'artifact mismatch'): ex.install(other,self.directory,self.now+1000)
        self.assertFalse(self.directory.exists())

    def test_partial_install_never_replaced(self):
        self.directory.mkdir(mode=0o700)
        publish(self.directory/ex.MODEL_NAME,self.sealed)
        with self.assertRaises(FileNotFoundError): ex.install(self.source,self.directory,self.now+1000)
        self.assertFalse((self.directory/ex.REGISTRATION_NAME).exists())

    def test_unsafe_permissions_symlink_and_clock_refused(self):
        ex.install(self.source,self.directory,self.now+1000)
        with self.assertRaisesRegex(ValueError,'clock regression'): ex.inspect(self.directory,self.now)
        p=self.directory/ex.MODEL_NAME; p.chmod(0o644)
        with self.assertRaisesRegex(ValueError,'Unsafe experiment file'): ex.inspect(self.directory,self.now+2000)
        p.chmod(0o600)
        link=self.root/'link'; link.symlink_to(self.directory)
        with self.assertRaisesRegex(ValueError,'private 0700'): ex.inspect(link,self.now+2000)

    def test_registration_tamper_and_false_live_flag_refused(self):
        ex.install(self.source,self.directory,self.now+1000)
        p=self.directory/ex.REGISTRATION_NAME
        r=ex.read_json(p,16384); r['testNotBeforeAt']-=1
        p.write_bytes(gzip.compress(json.dumps(r).encode()))
        with self.assertRaisesRegex(ValueError,'registration mismatch'): ex.inspect(self.directory,self.now+2000)
        r['testNotBeforeAt']+=1; r['liveUseAllowed']=True
        r['registrationSha256']=digest({k:v for k,v in r.items() if k!='registrationSha256'})
        p.write_bytes(gzip.compress(json.dumps(r).encode()))
        with self.assertRaisesRegex(ValueError,'registration mismatch'): ex.inspect(self.directory,self.now+2000)

    def test_evaluation_applies_later_host_boundary_never_refits(self):
        install_at=self.now+1000000
        info=ex.install(self.source,self.directory,install_at)
        start=info['registration']['testNotBeforeAt']; data=copy.deepcopy(self.data)
        template=data['rows'][0]; data['rows']=[]
        for i,at in enumerate((start-1,start)):
            row=copy.deepcopy(template); row.update(id='forward'+str(i),seq=1000+i,mint='new'+str(i),signalAt=at)
            row['targets']['30000']['availableAt']=at+31000
            data['rows'].append(row)
        data['capturedAt']=start+200000
        before=(self.directory/ex.MODEL_NAME).read_bytes()
        with patch('capture_review.combine',return_value=(data,{'captureCount':1})), patch('model.fit',side_effect=AssertionError('no fit')):
            out=ex.review(self.directory,[],data['capturedAt']+1)
        self.assertEqual(out['beforeExperimentStartExcluded'],{'baseline':1})
        self.assertEqual(out['groups'][0]['forwardWatches'],1)
        self.assertFalse(out['modelRefitted']); self.assertFalse(out['liveUseAllowed'])
        self.assertEqual(before,(self.directory/ex.MODEL_NAME).read_bytes())

    def test_future_capture_refused(self):
        ex.install(self.source,self.directory,self.now+1000)
        with patch('capture_review.combine',return_value=({'capturedAt':self.now+3000},{})):
            with self.assertRaisesRegex(ValueError,'future'): ex.review(self.directory,[],self.now+2000)

if __name__=='__main__': unittest.main()
