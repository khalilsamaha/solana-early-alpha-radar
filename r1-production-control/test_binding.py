import unittest
from unittest.mock import patch
import check_binding as b
from test_admission import evidence
from test_observed_target import PINS


class BindingTests(unittest.TestCase):
    def test_success_is_one_read_only_inspect_and_no_control(self):
        raw,data,sha=evidence();calls=[]
        def run(args,**kwargs):
            calls.append(args);kwargs['events'].append({'status':'completed','stderr_present':False})
            return b.c.raw(raw)
        with patch.object(b.accepted,'BASELINE_SHA256',sha),patch.object(b.accepted,'PRODUCER_PINS',PINS), \
             patch.object(b.ownership,'find_baseline',return_value=data),patch.object(b.ownership.i.host,'trusted_local_docker'), \
             patch.object(b.command_io,'bounded',side_effect=run),patch.object(b.a.control.Control,'__enter__',side_effect=AssertionError('mutation')):
            report=b.collect('/fixture')
        self.assertEqual(report['status'],'target-binding-observed-live-blocked');self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][-1],raw['id']);self.assertIn('inspect',calls[0])
        self.assertFalse(report['production_modified']);self.assertFalse(report['activation_authorized'])
    def test_baseline_failure_never_queries_docker_and_redacts(self):
        with patch.object(b.ownership,'find_baseline',side_effect=ValueError('private-fixture-secret')), \
             patch.object(b.command_io,'bounded',side_effect=AssertionError('docker')):
            report=b.collect('/fixture')
        self.assertEqual(report['failure'],{'stage':'accepted-baseline','code':'operation-unavailable'})
        self.assertNotIn('private-fixture-secret',b.c.raw(report).decode())
    def test_post_observation_source_drift_drops_binding(self):
        raw,data,sha=evidence()
        with patch.object(b,'pins',side_effect=[{'a':'a'*64},{'a':'b'*64}]), \
             patch.object(b.accepted,'BASELINE_SHA256',sha),patch.object(b.accepted,'PRODUCER_PINS',PINS), \
             patch.object(b.ownership,'find_baseline',return_value=data),patch.object(b.ownership.i.host,'trusted_local_docker'), \
             patch.object(b.command_io,'bounded',return_value=b.c.raw(raw)):
            report=b.collect('/fixture')
        self.assertEqual(report['failure'],{'stage':'source-after','code':'binding-source-changed'})
        self.assertNotIn('binding',report)
    def test_actual_admission_failure_retains_specific_category(self):
        raw,data,sha=evidence();raw['pid']=999
        with patch.object(b.accepted,'BASELINE_SHA256',sha),patch.object(b.accepted,'PRODUCER_PINS',PINS), \
             patch.object(b.ownership,'find_baseline',return_value=data),patch.object(b.ownership.i.host,'trusted_local_docker'), \
             patch.object(b.command_io,'bounded',return_value=b.c.raw(raw)):
            report=b.collect('/fixture')
        self.assertEqual(report['failure'],{'stage':'exact-target-binding','code':'admission-engine-target-drift'})
        self.assertNotIn('binding',report)

if __name__=='__main__':unittest.main()
