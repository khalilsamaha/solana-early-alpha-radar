"""Connected continuation transport, fail-closed boundaries and host command scope."""
import gzip,json,subprocess,sys,tempfile,unittest
from pathlib import Path

class ContinuationExitTests(unittest.TestCase):
    def test_connected_actual_backend(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.gz';cmd=[sys.executable,'-E','-s',str(Path(__file__).with_name('continuation_exit_cli.py')),'--output',str(out)]
            process=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr)
            raw=out.read_bytes();result=json.loads(gzip.decompress(raw))
            self.assertEqual(result['state'],'offline-integration-passed',result)
            self.assertEqual(result['casesPassed'],16)
            self.assertNotIn('failedPhase',result)
            self.assertTrue(all(r['completed'] for r in result['diagnosticPhases']))
            self.assertIn('replacement-preparation',[r['phase'] for r in result['diagnosticPhases']])
            self.assertEqual(len(result['independentContractCases']),14)
            self.assertTrue(result['collectionSignatureVerification']['sharedWithParent'])
            phases={row['phase']:row for row in result['diagnosticPhases']}
            self.assertEqual(phases['continuation-signing-handoff']['signatureVerification']['verifierProcesses'],1)
            self.assertEqual(phases['continuation-submission']['signatureVerification']['verifierProcesses'],0)
            self.assertEqual(phases['continuation-submission']['preservedGenerationReads'],8)
            self.assertGreater(result['signatureVerification']['memoHits'],0)
            self.assertTrue(result['temporaryLedgersRemoved'])
            self.assertEqual(result['realNetworkRequests'],0)
            self.assertFalse(result['productionWalletAccessed'])
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            self.assertEqual(out.read_bytes(),raw)
            print('Connected continuation/sign/send diagnostic ms:',result['integrationElapsedMs'])
    def test_cli_rejects_operational_scope(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.gz';cmd=[sys.executable,'-E','-s',str(Path(__file__).with_name('continuation_exit_cli.py')),'--output',str(out)]
            for flag in ('--action','--directory','--wallet','--pool','--expected-original-sha256','--expected-current-sha256','--allow-unsigned-continuation','--allow-private-key-signing','--allow-devnet-submit'):
                self.assertNotEqual(subprocess.run(cmd+[flag],capture_output=True).returncode,0)
                self.assertFalse(out.exists())

    def test_generation_options_are_exclusive_before_access(self):
        from unittest.mock import patch
        import fresh_exit as m
        with patch.object(m.view.cycles.c,'source_lock',side_effect=AssertionError('source')):
            with self.assertRaises(ValueError):
                m.replace_sign_submit('/missing','w','p',expected_preparation_sha256='a'*64,
                    allow_unsigned_replacement=True,allow_private_key_signing=True,allow_devnet_submit=True,
                    _continuation_expected=('a'*64,'b'*64))
            for pair in (('a'*64,'a'*64),(None,'b'*64),('a'*64,'X'*64)):
                with self.assertRaises(ValueError):
                    m.continue_sign_submit('/missing','w','p',expected_original_sha256=pair[0],
                        expected_current_sha256=pair[1],allow_unsigned_continuation=True,
                        allow_private_key_signing=True,allow_devnet_submit=True)
            for option in ('_replacement_expected','_continuation_expected'):
                with self.assertRaises(ValueError):
                    m.continue_sign_submit('/missing','w','p',expected_original_sha256='a'*64,
                        expected_current_sha256='b'*64,allow_unsigned_continuation=True,
                        allow_private_key_signing=True,allow_devnet_submit=True,**{option:None})
            with self.assertRaises(ValueError):
                m._run('/missing','w','p',signer_adapter=None,
                    _replacement_expected='a'*64,_continuation_expected=('a'*64,'b'*64))

if __name__=='__main__':unittest.main()
