import copy
import json
import unittest
from unittest.mock import patch
import observed_target as t

PINS = {'r1-production-review/readiness.py': 'a' * 64,
        'scripts/r1-production-readiness-kali.sh': 'b' * 64}


def fixture(minute=0):
    start = f'2026-11-16T09:{minute:02d}:00+00:00'
    end = f'2026-11-16T09:{minute:02d}:01+00:00'
    metadata = {'id': 'a'*64, 'image': 'sha256:'+'b'*64, 'name': '/'+t.i.host.TARGET,
        'pid': 123, 'running': True, 'started': '2026-11-01T00:00:00Z', 'user': 'node',
        'working_dir': '/app', 'project': t.i.PROJECT, 'service': t.i.SERVICE,
        'readonly_rootfs': True, 'privileged': False, 'init': True,
        'restart_policy': 'unless-stopped', 'memory': 512*1024**2, 'memory_swap': 1024*1024**2,
        'nano_cpus': 0, 'pids_limit': None, 'network_mode': 'radar_default',
        'mounts': [{'type': 'volume', 'source': '/var/lib/docker/volumes/radar_data/_data',
                    'destination': '/app/data', 'rw': True}]}
    process = {'pid': 123, 'start_ticks': 20, 'uid': [1000]*4, 'gid': [1000]*4,
               'user_namespace': 'user:[1234]'}
    identity = {'container': copy.deepcopy(metadata), 'container_cgroup_binding_observed': True,
                'same_uid_and_namespace_observed': True, 'init_process': process,
                'main_process': {**process, 'pid': 124}}
    context = {'schema': 1, 'kind': 'read-only-production-context', 'started_utc': start, 'finished_utc': end,
               'target': t.i.host.TARGET, 'metadata': metadata, 'metadata_sha256': t.i.digest(t.i.raw(metadata)),
               'same_projection_observed_twice': True,
               'source_sha256': {'r1-production-review/readiness.py': 'a'*64},
               'identity_observation': identity,
               **{k: False for k in (*t.FALSE_FLAGS, 'sole_owner_verified',
                                    'full_configuration_verified', 'production_ipc_peer_verified')}}
    config = {'container_id': metadata['id'], 'image': metadata['image'], 'started': metadata['started'],
              'configuration_sha256': 'c'*64, 'raw_environment_exported': False, 'raw_command_exported': False,
              'command_is_node_scanner': True, 'working_directory_is_app': True,
              'configured_source_mode': 'direct-default', 'shared_socket_configured': False,
              'data_volume_name': 'radar_data', 'compose_directory': '/home/user/apps/radar',
              'compose_files': ['/home/user/apps/radar/compose.yaml']}
    observation = {'kind': 'r1-production-deployment-inputs', 'source_sha256': PINS,
                   'started_utc': start, 'finished_utc': end, 'context': context,
                   'configuration': config, 'running_container_ids': ['a'*64, 'd'*64],
                   **{k: False for k in (*t.FALSE_FLAGS, 'container_exec_used', 'credentials_exported',
                       'full_effective_configuration_verified', 'global_owner_exclusivity_verified')}}
    return {'schema_version': 2, 'status': 'deployment-inputs-observed-rollout-pending',
            'observation_attempted': True, 'source_sha256': PINS, 'started_utc': start, 'finished_utc': end,
            'stages': [{'stage': name, 'status': 'completed', 'started_utc': start, 'finished_utc': start}
                       for name in t.STAGES], 'observation': observation,
            **{k: False for k in (*t.FALSE_FLAGS, 'automatic_resume_allowed', 'raw_diagnostics_exported')}}


def encode(row):
    data = t.m.raw(row)
    return data, t.m.digest(data)


class ObservedTargetTests(unittest.TestCase):
    def bind(self, row):
        return t.bind(*encode(row), PINS)

    def compare(self, new, old=None):
        a, ah = encode(old or fixture())
        b, bh = encode(new)
        return t.compare(a, ah, b, bh, PINS)

    def test_binds_exact_target_volume_and_compose_without_live_authority(self):
        result = self.bind(fixture())
        self.assertEqual(result['target']['data_volume_name'], 'radar_data')
        self.assertEqual(result['target']['compose_files'], ['/home/user/apps/radar/compose.yaml'])
        self.assertEqual(result['unreviewed_other_container_ids'], ['d'*64])
        for key in ('activation_authorized', 'automatic_resume_allowed', 'rollback_artifact_verified',
                    'global_owner_exclusivity_verified', 'full_configuration_verified'):
            self.assertIs(result[key], False)

    def test_matching_later_observation_is_only_a_read_only_comparison(self):
        result = self.compare(fixture(1))
        self.assertTrue(result['same_target_observed'])
        self.assertFalse(result['activation_authorized'])

    def test_replayed_or_overlapping_observation_cannot_satisfy_fresh_guard(self):
        for minute in (0,):
            with self.assertRaisesRegex(ValueError, 'fresh-observation-required'):
                self.compare(fixture(minute))
        old = fixture(1)
        with self.assertRaisesRegex(ValueError, 'fresh-observation-required'):
            self.compare(fixture(0), old)

    def test_configuration_compose_volume_and_process_drift_refuse(self):
        changes = (
            lambda o: o['configuration'].update(configuration_sha256='e'*64),
            lambda o: o['configuration'].update(data_volume_name='other_data'),
            lambda o: o['configuration'].update(compose_files=['/other/compose.yaml']),
            lambda o: o['context']['identity_observation']['main_process'].update(start_ticks=21),
        )
        for change in changes:
            row = fixture(1); change(row['observation'])
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'target-drift'):
                self.compare(row)

    def test_added_other_container_invalidates_prior_ownership_review_set(self):
        row = fixture(1); row['observation']['running_container_ids'].append('e'*64)
        with self.assertRaisesRegex(ValueError, 'ownership-census-drift'):
            self.compare(row)

    def test_inaccessible_and_not_run_stages_never_become_binding(self):
        for status in ('not-run', 'unavailable', 'started'):
            row = fixture(); row['stages'][3]['status'] = status
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.bind(row)

    def test_failed_report_and_missing_exact_digest_refuse(self):
        row = fixture(); row['status'] = 'deployment-inputs-unavailable'
        with self.assertRaises(ValueError): self.bind(row)
        raw, _ = encode(fixture())
        with self.assertRaisesRegex(ValueError, 'report-digest'): t.bind(raw, '0'*64, PINS)

    def test_producer_and_nested_fingerprints_must_agree(self):
        for part in ('source_sha256', 'nested'):
            row = copy.deepcopy(fixture())
            if part == 'nested': row['observation']['context']['source_sha256'] = {}
            else: row['source_sha256'] = {'other.py': 'f'*64}
            with self.subTest(part=part), self.assertRaises(ValueError): self.bind(row)

    def test_new_producer_requires_separately_reviewed_pins_without_relabelling_baseline(self):
        new = copy.deepcopy(fixture(1)); pins = {**PINS, 'r1-production-review/new.py': 'f'*64}
        new['source_sha256'] = pins; new['observation']['source_sha256'] = pins
        new['observation']['context']['source_sha256']['r1-production-review/new.py'] = 'f'*64
        a, ah = encode(fixture()); b, bh = encode(new)
        with self.assertRaisesRegex(ValueError, 'producer-mismatch'):
            t.compare(a, ah, b, bh, PINS)
        self.assertTrue(t.compare(a, ah, b, bh, PINS, fresh_producer_pins=pins)['same_target_observed'])

    def test_identity_metadata_digest_and_shared_mode_conflicts_refuse(self):
        for field in ('metadata', 'identity', 'mode'):
            row = fixture(); o = row['observation']
            if field == 'metadata': o['context']['metadata_sha256'] = '0'*64
            elif field == 'identity': o['configuration']['container_id'] = '0'*64
            else: o['configuration']['configured_source_mode'] = 'shared'
            with self.subTest(field=field), self.assertRaises(ValueError): self.bind(row)

    def test_authority_flags_cannot_be_imported_from_report(self):
        for layer in ('root', 'observation', 'context'):
            row = fixture()
            scope = row if layer == 'root' else row['observation'] if layer == 'observation' else row['observation']['context']
            scope['activation_authorized'] = True
            with self.subTest(layer=layer), self.assertRaises(ValueError): self.bind(row)

    def test_unknown_process_values_and_unsafe_compose_locations_refuse(self):
        for field in ('uid', 'namespace', 'compose'):
            row = fixture(); o = row['observation']
            if field == 'uid': o['context']['identity_observation']['main_process']['uid'] = ['secret']*4
            elif field == 'namespace': o['context']['identity_observation']['main_process']['user_namespace'] = 'secret'
            else: o['configuration']['compose_files'] = ['/a/../b/compose.yaml']
            with self.subTest(field=field), self.assertRaises(ValueError): self.bind(row)

    def test_compare_does_not_open_processes_or_write_files(self):
        with patch('subprocess.Popen', side_effect=AssertionError('process')), \
             patch('os.open', side_effect=AssertionError('filesystem')):
            self.assertTrue(self.compare(fixture(1))['same_target_observed'])

    def test_output_has_no_environment_values_and_is_not_aliased(self):
        row = fixture(); row['observation']['configuration']['environment_variable_names'] = ['PRIVATE']
        result = self.bind(row)
        self.assertNotIn('PRIVATE', json.dumps(result))
        row['observation']['context']['metadata']['mounts'][0]['source'] = '/changed'
        self.assertNotEqual(result['target']['metadata']['mounts'][0]['source'], '/changed')


if __name__ == '__main__': unittest.main()
