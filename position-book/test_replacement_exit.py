"""Connected replacement transport, fail-closed boundaries and host command scope."""
import gzip,json,subprocess,sys,tempfile,unittest
from pathlib import Path

class ReplacementExitTests(unittest.TestCase):
    def test_connected_actual_backend(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.gz';cmd=[sys.executable,'-E','-s',str(Path(__file__).with_name('replacement_exit_cli.py')),'--output',str(out)]
            process=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr)
            raw=out.read_bytes();result=json.loads(gzip.decompress(raw))
            self.assertEqual(result['state'],'offline-integration-passed',result)
            self.assertEqual(result['casesPassed'],12)
            self.assertEqual(len(result['independentContractCases']),10)
            self.assertTrue(result['temporaryLedgersRemoved'])
            self.assertEqual(result['realNetworkRequests'],0)
            self.assertFalse(result['productionWalletAccessed'])
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            self.assertEqual(out.read_bytes(),raw)
            print('Connected replacement/sign/send diagnostic ms:',result['integrationElapsedMs'])
    def test_cli_rejects_operational_scope(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.gz';cmd=[sys.executable,'-E','-s',str(Path(__file__).with_name('replacement_exit_cli.py')),'--output',str(out)]
            for flag in ('--action','--directory','--wallet','--pool','--allow-unsigned-replacement','--allow-private-key-signing','--allow-devnet-submit'):
                self.assertNotEqual(subprocess.run(cmd+[flag],capture_output=True).returncode,0)
                self.assertFalse(out.exists())

if __name__=='__main__':unittest.main()
