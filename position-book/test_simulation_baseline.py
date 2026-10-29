"""Updated deployment observation cannot update other pins or bypass effect checks."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import fresh_quote as m
import simulation_baseline
from program import deployment
import test_fresh_quote as fixtures
from test_fresh_quote import setup, edit
from test_unsigned_simulation import SimulationOpener


class SimulationBaselineTests(unittest.TestCase):
    def observe(self, **kw):
        return fixtures.FreshQuoteTests().run_observe(simulate=True,
            opener_factory=lambda f,s,scope: SimulationOpener(f,s,scope), **kw)

    def test_explicit_selection_accepts_observed_bytes_without_mutating_legacy_pin(self):
        before=deepcopy((m.preflight.BASELINE,m.preflight_capture.BASELINE,simulation_baseline.BASELINE))
        r,o=self.observe(refreshed_deployment=True,legacy_mismatch=True)
        self.assertEqual(r['state'],'unsigned-quote-simulation-consistent',r)
        self.assertTrue(r['simulationDeploymentRefresh']);self.assertEqual(len(o.calls),20)
        self.assertEqual((m.preflight.BASELINE,m.preflight_capture.BASELINE,simulation_baseline.BASELINE),before)
        self.assertFalse(r['executionApproved']);self.assertEqual(r['transactionsSent'],0)
        r,o=self.observe(legacy_mismatch=True)
        self.assertEqual(r['state'],'unavailable');self.assertEqual(len(o.calls),4)
        self.assertFalse(r['simulationDeploymentRefresh'])

    def test_further_deployment_change_blocks_at_both_captures(self):
        for phase,count in [('first',4),('second',14)]:
            def change(f,s,scope):edit(f if phase=='first' else s,-1,120,b'\x01')
            r,o=self.observe(refreshed_deployment=True,mutate=change)
            self.assertEqual(r['state'],'unavailable',r)
            # The second collector stops at its account batch; no simulated request follows.
            self.assertFalse(r['simulationVerified'])
            self.assertNotIn('simulateTransaction',[v['method'] for v in o.calls])
            self.assertEqual(len(o.calls),count)

    def test_actual_observed_allocation_size_fits_existing_bounds(self):
        f,s,b,scope=setup()
        def extend(c):
            row=c['evidence']['accounts']['result']['value'][-1]
            raw=base64.b64decode(row['data'][0]);raw+=bytes(1766685-len(raw))
            row['data'][0]=base64.b64encode(raw).decode()
        extend(f)
        b['identity'].update({k:v for k,v in deployment(f['evidence']['accounts']['result']['value'][-1],101).items()
                              if k in b['identity']})
        def change(first,second,scope):extend(first);extend(second)
        r,o=self.observe(refreshed_deployment=True,selected_base=b,mutate=change)
        self.assertEqual(r['state'],'unsigned-quote-simulation-consistent',r)
        self.assertEqual(len(o.calls),20)

    def test_flag_cannot_select_refreshed_pin_in_readonly_or_offline_modes(self):
        with self.assertRaisesRegex(ValueError,'requires-unsigned-simulation'):
            m.observe(Path('/not-used'),'wallet','pool',refreshed_deployment=True)
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'check.json.gz'
            p=subprocess.run([sys.executable,'-E','-s',str(Path(__file__).with_name('simulation_cli.py')),
                '--deployment-observation-20261027','--output',str(out)],capture_output=True,timeout=15)
            self.assertNotEqual(p.returncode,0);self.assertFalse(out.exists())

    def test_observation_provenance_and_legacy_pin_are_distinct(self):
        b=simulation_baseline.BASELINE
        self.assertEqual(b['sourceCaptureSha256'],'8fd7e3437cd2fc4641a5e121267d52138e3e47e656daf7d38f91201c288e6294')
        self.assertEqual(b['observedSlot'],515785731)
        self.assertEqual(b['identity']['deploymentSlot'],515685818)
        self.assertEqual(b['identity']['payloadSha256'],'30a9273dda17d7b3513889af1dab1185d9facc4756a6edf36c42f30ba228d8d1')
        self.assertEqual(m.preflight.BASELINE['identity']['deploymentSlot'],498629438)
        self.assertEqual(m.preflight_capture.BASELINE,m.preflight.BASELINE)


if __name__=='__main__':unittest.main()
