import io
import json
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import patch

import inventory as inv


def resource_row(**changes):
    return {'id':'a'*64,'image':inv.BASELINE_IMAGE,'pid':123,'running':True,
            'started':'2026-11-13T08:40:00.000000000Z','restart_policy':'unless-stopped',
            'memory':0,'memory_swap':0,'pids_limit':None,'nano_cpus':0,**changes}


def identity():
    base=resource_row()
    return {'container':{k:base[k] for k in ('id','image','pid','running','started','restart_policy')},
            'init_process':{'pid':123,'start_ticks':100},'main_process':{'pid':124,'start_ticks':101},
            'review_user':{'uid':1000,'user_namespace':'user:[1]'},'findings':[],
            'production_ipc_peer_verified':False,'process_executable_verified':False}


def observation():
    return {'identity':identity(),'container_resource_settings':resource_row(),
            'memory_sample':{'allocation_or_reservation_proven':False},
            'storage_sample':{'production_storage_measured':False},
            'matches_prior_offline_image':True,'resource_settings_stable_across_reads':True,
            'global_connection_owner_verified':False,'provider_socket_closed_verified':False,
            'stable_registry_bound':False,'production_endpoint_bound':False,'credential_provisioning_verified':False}


class InventoryTests(unittest.TestCase):
    def test_zero_failure_test_run_with_diagnostic_cannot_clear_observation_gate(self):
        def emits(): print('TimeoutError exception in shielded future',file=sys.stderr)
        suite=unittest.TestSuite([unittest.FunctionTestCase(emits)])
        with patch.object(inv.unittest.defaultTestLoader,'discover',return_value=suite):
            with self.assertRaises(inv.host.ReviewError):inv.run_tests()

    def test_resource_query_is_fixed_local_inspect_with_no_sensitive_fields(self):
        with patch.object(inv.host,'bounded_command',return_value=json.dumps(resource_row()).encode()) as call:
            self.assertEqual(inv.resources(Path('/private/config')),resource_row())
        self.assertEqual(call.call_args.args[0],[inv.host.DOCKER,'--config','/private/config','--host',
            'unix:///run/docker.sock','inspect','--type','container','--format',inv.FORMAT,inv.host.TARGET])
        for forbidden in ('.Env','.Cmd','.Entrypoint','.Mounts','.Labels','.Args'):
            self.assertNotIn(forbidden,inv.FORMAT)

    def test_invalid_or_extra_resource_fields_are_rejected(self):
        for change in ({'memory':True},{'memory':-1},{'memory_swap':-2},{'pids_limit':'unlimited'},
                       {'nano_cpus':2**63},{'running':False},{'pid':0},{'extra':'private'},
                       {'image':'not-an-image'},{'restart_policy':'unsafe'}):
            with self.subTest(change=change), patch.object(inv.host,'bounded_command',return_value=json.dumps(resource_row(**change)).encode()):
                with self.assertRaises(inv.host.ReviewError): inv.resources(Path('/private/config'))

    def test_unlimited_daemon_values_are_recorded_without_approval(self):
        row=resource_row(memory_swap=-1,pids_limit=-1)
        with patch.object(inv.host,'bounded_command',return_value=json.dumps(row).encode()):
            self.assertEqual(inv.resources(Path('/private/config')),row)
        pending=inv.prerequisites(observation())
        self.assertEqual(pending['status'],'production-handoff-blocked')
        self.assertEqual(pending['open_gates'],list(inv.OPEN_GATES))
        self.assertFalse(pending['live_launch_authorized'])

    def collect(self,rows=None,who=None):
        with patch.object(inv.host,'trusted_local_docker'), \
             patch.object(inv,'resources',side_effect=rows or [resource_row(),resource_row()]), \
             patch.object(inv.host,'observe',return_value=who or identity()), \
             patch.object(inv,'memory_sample',return_value={'scope':'test'}), \
             patch.object(inv,'storage_sample',return_value={'scope':'test'}):
            return inv.observe(Path('/private/config'),Path('/private/output'))

    def test_stable_observation_never_establishes_connection_or_registry(self):
        row=self.collect()
        for key in ('global_connection_owner_verified','provider_socket_closed_verified','stable_registry_bound',
                    'production_endpoint_bound','credential_provisioning_verified'):
            self.assertFalse(row[key])
        self.assertTrue(row['matches_prior_offline_image'])

    def test_resource_or_identity_change_rejects_mixed_observations(self):
        for change in ({'id':'b'*64},{'pid':124},{'started':'2026-11-13T08:41:00.000000000Z'},
                       {'restart_policy':'always'},{'memory':1024}):
            with self.subTest(change=change), self.assertRaises(inv.host.ReviewError):
                self.collect([resource_row(),resource_row(**change)])
        who=identity();who['container']['id']='b'*64
        with self.assertRaises(inv.host.ReviewError): self.collect(who=who)

    def test_image_change_is_a_finding_not_an_automatic_rejection_or_approval(self):
        row=resource_row(image='sha256:'+'b'*64);who=identity();who['container']['image']=row['image']
        observed=self.collect([row,row],who)
        pending=inv.prerequisites(observed)
        self.assertIn('image-differs-from-prior-offline-baseline',pending['observed_findings'])
        self.assertFalse(pending['full_gate_accepted'])

    def test_memory_reads_only_bounded_allowlisted_proc_fields(self):
        with patch.object(inv.host,'read_proc',return_value='MemTotal: 4096 kB\nMemAvailable: 2048 kB\nOther: 123\n') as read:
            result=inv.memory_sample()
        read.assert_called_once_with('/proc/meminfo')
        self.assertEqual(result['available_bytes'],2048*1024)
        self.assertFalse(result['allocation_or_reservation_proven'])

    def test_missing_duplicate_or_inconsistent_memory_is_unavailable(self):
        for text in ('MemTotal: 4096 kB\n','MemTotal: 2 kB\nMemAvailable: 3 kB\n',
                     'MemTotal: 4 kB\nMemTotal: 4 kB\nMemAvailable: 1 kB\n'):
            with patch.object(inv.host,'read_proc',return_value=text):
                with self.assertRaises(inv.host.ReviewError):inv.memory_sample()

    def test_output_disk_sample_cannot_claim_production_capacity(self):
        with tempfile.TemporaryDirectory() as tmp: result=inv.storage_sample(tmp)
        self.assertEqual(result['scope'],'review-output-filesystem-only')
        self.assertFalse(result['production_storage_measured'])
        self.assertFalse(result['allocation_or_reservation_proven'])

    def test_unavailable_inventory_keeps_every_gate_open(self):
        pending=inv.prerequisites(None)
        self.assertTrue(pending['observation_missing'])
        self.assertIsNone(pending['candidate_identity_binding'])
        self.assertEqual(pending['open_gates'],list(inv.OPEN_GATES))
        for key in ('live_launch_authorized','automatic_rollback_allowed','production_actions_performed','funding_authorized','full_gate_accepted'):
            self.assertFalse(pending[key])

    def test_cli_publishes_bound_reports_without_service_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'results'
            with patch.object(inv,'run_tests',return_value=({'run':1,'failures':0,'errors':0,'skipped':0},b'offline fixture\n')), \
                 patch.object(inv,'observe',return_value=observation()) as observe, \
                 patch.object(inv.host,'bounded_command') as command, patch('sys.stdout',new=io.StringIO()):
                self.assertEqual(inv.main(['--observe-local-container','--output-directory',str(output)]),0)
                observe.assert_called_once();command.assert_not_called()
            report=json.loads((output/'report.json').read_bytes())
            self.assertEqual(report['prerequisites_sha256'],inv.host.sha((output/'prerequisites.json').read_bytes()))
            self.assertEqual(report['status'],'handoff-inventory-observed-rollout-blocked')
            self.assertFalse(report['production_modified'])
            self.assertEqual(report['docker_inspection_budget'],4)

    def test_unavailable_daemon_retains_fixed_error_without_secret_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'results'
            with patch.object(inv,'run_tests',return_value=({'run':1},b'fixture\n')), \
                 patch.object(inv,'observe',side_effect=RuntimeError('SYNTHETIC-PRIVATE-ERROR')), \
                 patch('sys.stdout',new=io.StringIO()):
                self.assertEqual(inv.main(['--observe-local-container','--output-directory',str(output)]),0)
            report=json.loads((output/'report.json').read_bytes())
            self.assertEqual(report['status'],'handoff-inventory-unavailable-rollout-blocked')
            self.assertEqual(report['error'],'inventory-observation-unavailable')
            self.assertIsNone(report['observation'])
            for p in output.iterdir():self.assertNotIn(b'SYNTHETIC-PRIVATE-ERROR',p.read_bytes())

    def test_existing_output_refuses_to_observe_or_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'results';output.mkdir();(output/'keep').write_bytes(b'unchanged')
            with patch.object(inv,'observe') as observe, patch('sys.stderr',new=io.StringIO()):
                self.assertEqual(inv.main(['--observe-local-container','--output-directory',str(output)]),1)
                observe.assert_not_called()
            self.assertEqual((output/'keep').read_bytes(),b'unchanged')

    def test_source_drift_never_publishes_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'results'
            with patch.object(inv,'run_tests',return_value=({'run':1},b'fixture\n')), \
                 patch.object(inv,'pins',side_effect=[{'test':'a'},{'test':'b'}]), \
                 patch.object(inv,'observe',return_value=observation()), patch('sys.stderr',new=io.StringIO()):
                self.assertEqual(inv.main(['--observe-local-container','--output-directory',str(output)]),1)
            self.assertFalse((output/'report.json').exists())


if __name__=='__main__':unittest.main()
