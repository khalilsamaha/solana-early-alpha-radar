import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CLI=Path(__file__).with_name('rehearsal_cli.py')


class CliTests(unittest.TestCase):
    def invoke(self,*args):
        return subprocess.run([sys.executable,'-E','-s',str(CLI),*map(str,args)],capture_output=True,text=True,timeout=20)
    def test_actual_cli_uses_correct_twelve_case_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'report.json.gz';r=self.invoke('--output',out)
            self.assertEqual(r.returncode,0,r.stderr)
            d=json.loads(gzip.decompress(out.read_bytes()))
            self.assertEqual(d['format'],'devnet-swap-rehearsal-self-check-1');self.assertEqual(d['casesPassed'],12)
            self.assertFalse(d['realWalletAccessed']);self.assertEqual(d['publicRpcRequests'],0)
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(self.invoke('--output',out).returncode,0)
    def test_prepare_requires_explicit_sign_flag_before_directory_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'out.json.gz'
            r=self.invoke('--action','prepare','--directory',Path(tmp)/'absent','--wallet','unused','--output',out)
            self.assertNotEqual(r.returncode,0);self.assertFalse(out.exists());self.assertFalse((Path(tmp)/'absent').exists())
    def test_inventory_cannot_enable_signing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'out.json.gz'
            self.assertNotEqual(self.invoke('--action','inventory','--allow-devnet-sign','--output',out).returncode,0)
            self.assertFalse(out.exists())
    def test_self_check_rejects_real_wallet_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'out.json.gz'
            self.assertNotEqual(self.invoke('--directory',tmp,'--output',out).returncode,0)
            self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
