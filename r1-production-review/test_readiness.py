import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import readiness as r


def config():
    return {'id': 'a'*64, 'image': 'sha256:'+'b'*64, 'started': '2026-11-16T00:00:00Z',
            'cmd': ['node', 'src/index.js'], 'entrypoint': ['docker-entrypoint.sh'],
            'environment': ['PUMPPORTAL_API_KEY=SECRET-NEVER-EXPORT', 'DATA_DIR=/app/data'],
            'working_dir': '/app', 'ports': {'8787/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8787'}]},
            'tmpfs': {'/tmp': 'size=32m'}, 'caps_drop': ['ALL'], 'caps_add': None,
            'security': ['no-new-privileges'], 'stop_signal': None, 'stop_timeout': 35,
            'mounts': [{'Type': 'volume', 'Destination': '/app/data', 'Name': 'existing_radar_data'}],
            'compose_directory': '/home/user/apps/radar', 'compose_files': '/home/user/apps/radar/compose.yaml'}


class ReadinessTests(unittest.TestCase):
    def project(self, row):
        with patch.object(r.diagnostics, 'command', return_value=json.dumps(row).encode()):
            return r.configuration(Path('/unused'))

    def test_secret_values_are_fingerprinted_but_never_exported(self):
        row = config(); result = self.project(row)
        self.assertNotIn('SECRET-NEVER-EXPORT', json.dumps(result))
        self.assertTrue(result['provider_credential_present'])
        self.assertTrue(result['command_is_node_scanner'])
        self.assertEqual(result['configured_source_mode'], 'direct-default')
        self.assertEqual(result['data_volume_name'], 'existing_radar_data')
        self.assertEqual(result['stop_timeout_seconds'], 35)
        row['environment'][0] += '-CHANGED'
        self.assertNotEqual(result['configuration_sha256'], self.project(row)['configuration_sha256'])

    def test_unknown_modes_and_commands_do_not_escape_in_reports(self):
        row = config(); row['cmd'] = ['secret-command']; row['environment'].append('PUMPPORTAL_SOURCE=secret-mode')
        result = self.project(row)
        self.assertFalse(result['command_is_node_scanner'])
        self.assertEqual(result['configured_source_mode'], 'unrecognized')
        self.assertNotIn('secret-', json.dumps(result))

    def test_duplicate_environment_names_refuse_instead_of_ambiguous_effective_config(self):
        row = config(); row['environment'].append('DATA_DIR=/different')
        with self.assertRaises(ValueError): self.project(row)

    def test_public_dashboard_or_added_capability_not_accepted(self):
        row = config(); row['ports']['8787/tcp'][0]['HostIp'] = '0.0.0.0'; row['caps_add'] = ['SYS_ADMIN']
        result = self.project(row)
        self.assertFalse(result['dashboard_loopback_only']); self.assertFalse(result['all_capabilities_dropped'])

    def test_census_covers_all_running_containers_without_project_filter(self):
        with patch.object(r.diagnostics, 'command', return_value=('a'*64+'\n'+'b'*64+'\n').encode()) as call:
            self.assertEqual(len(r.census(Path('/unused'))), 2)
        self.assertNotIn('--filter', call.call_args.args)

    def test_storage_observation_never_creates_a_missing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp)/'missing'
            self.assertFalse(r.storage(missing)['available']); self.assertFalse(missing.exists())
            sample = r.storage(Path(tmp))
            self.assertTrue(sample['available']); self.assertFalse(sample['space_reserved'])

    def test_storage_symlink_and_dotenv_permission_failure_are_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp)/'linked'; link.symlink_to(tmp)
            self.assertFalse(r.storage(link)['available'])
        with patch.object(Path, 'lstat', side_effect=PermissionError):
            self.assertIsNone(r.dotenv_presence(123)['present'])

    def test_config_drift_refuses_even_when_container_id_is_unchanged(self):
        first = self.project(config()); second = {**first, 'configuration_sha256': 'f'*64}
        with patch.object(r.i.host, 'trusted_local_docker'), patch.object(r, 'configuration', side_effect=[first, second]), \
             patch.object(r, 'census', return_value=['a'*64]), patch.object(r.i, 'observe', return_value={
                 'identity_observation': {'main_process': {'pid': 123}}, 'metadata': {'mounts': []}}), \
             patch.object(r, 'dotenv_presence'), patch.object(r, 'storage'):
            with self.assertRaisesRegex(ValueError, 'configuration-changed'):
                r.observe(Path('/unused'), Path('/unused'))

    def test_unknown_volume_and_compose_paths_are_explicitly_missing(self):
        row = config(); row['mounts'] = []; row['compose_directory'] = None; row['compose_files'] = 'relative.yml'
        result = self.project(row)
        self.assertIsNone(result['data_volume_name']); self.assertIsNone(result['compose_directory'])
        self.assertEqual(result['compose_files'], [])

    def test_omitted_optional_leaves_remain_unknown_without_losing_identity(self):
        # JSON null is the projection of a missing map key; this exercises the
        # Python adapter, not a substitute implementation of Go's template engine.
        row = config()
        for key in (*r.CONFIG_FIELDS, *r.HOST_FIELDS, 'mounts', 'compose_directory', 'compose_files'):
            row[key] = None
        result = self.project(row)
        self.assertEqual(result['container_id'], 'a' * 64)
        self.assertIsNone(result['standard_term_signal'])
        self.assertIsNone(result['stop_timeout_seconds'])
        self.assertIsNone(result['data_volume_name'])
        self.assertIsNone(result['compose_directory'])
        self.assertEqual(result['compose_files'], [])
        self.assertEqual(result['environment_variable_names'], [])
        for key in ('command_is_node_scanner', 'all_capabilities_dropped',
                    'no_new_privileges', 'dashboard_loopback_only', 'tmpfs_tmp_configured'):
            self.assertIs(result[key], False)

    def test_missing_stop_signal_is_unknown_and_explicit_signals_are_compared(self):
        for value, expected in ((None, None), ('', None), ('SIGTERM', True), ('15', True),
                                ('SIGKILL', False), ('SECRET-UNKNOWN-SIGNAL', False)):
            with self.subTest(value=value):
                result = self.project({**config(), 'stop_signal': value})
                self.assertIs(result['standard_term_signal'], expected)
                self.assertNotIn('SECRET-UNKNOWN-SIGNAL', json.dumps(result))

    def test_missing_or_unsupported_timeout_does_not_invent_default(self):
        for value in (None, 0, -1, True, '30', 301):
            with self.subTest(value=value):
                result = self.project({**config(), 'stop_timeout': value})
                self.assertIsNone(result['stop_timeout_seconds'])

    def test_null_lists_are_supported_but_malformed_lists_and_missing_identity_refuse(self):
        for field in ('environment', 'mounts'):
            for value in ('not-a-list', {}, 7):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.project({**config(), field: value})
        for field in ('id', 'image', 'started'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.project({**config(), field: None})
