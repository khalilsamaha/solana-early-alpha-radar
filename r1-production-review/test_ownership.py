from contextlib import ExitStack
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
import ownership as o
import test_observed_target as fixtures


def workload(identity='a'*64):
    return {'id': identity, 'image': 'sha256:'+'b'*64, 'name': '/example-workload',
            'image_reference': 'example/app:1', 'running': True, 'pid': 123,
            'network_mode': 'example_default', 'project': 'example', 'service': 'app'}


class OwnershipTests(unittest.TestCase):
    def collect(self, *, rows=None, census=None, pins=None):
        baseline, sha = fixtures.encode(fixtures.fixture())
        members = ['a'*64, 'd'*64]
        with ExitStack() as stack:
            stack.enter_context(patch.object(o.i.host, 'trusted_local_docker'))
            stack.enter_context(patch.object(o, 'pins', side_effect=pins or [{'test.py': 'f'*64}]*2))
            stack.enter_context(patch.object(o.r, 'census', side_effect=census or [members, members]))
            inventory = stack.enter_context(patch.object(o, 'inventory', return_value=rows or
                [workload('a'*64), workload('d'*64)]))
            result = o.collect(Path('/unused'), baseline, sha)
            return result, inventory.call_count

    def test_complete_inventory_retains_review_hold_and_excluded_scope(self):
        report, calls = self.collect()
        self.assertEqual(calls, 1)
        self.assertEqual(report['status'], 'ownership-inventory-observed-review-pending')
        self.assertEqual(report['review_required_container_ids'], ['d'*64])
        self.assertEqual(report['docker_request_count'], 3)
        self.assertIn('host-processes', report['excluded_scope'])
        for key in ('global_owner_exclusivity_verified', 'activation_authorized', 'environment_read',
                    'command_values_read', 'container_exec_used', 'provider_connection_opened', 'production_modified'):
            self.assertIs(report[key], False)

    def test_census_change_during_observation_discards_partial_workloads_without_retry(self):
        report, calls = self.collect(census=[['a'*64, 'd'*64], ['a'*64, 'e'*64]])
        self.assertEqual(calls, 1)
        self.assertNotIn('workloads', report)
        self.assertEqual(report['failure'], {'stage': 'census-after', 'code': 'ownership-census-changed'})

    def test_new_container_since_baseline_is_observed_and_marked_for_review(self):
        members = ['a'*64, 'd'*64, 'e'*64]
        report, _ = self.collect(census=[members, members], rows=[workload(v) for v in members])
        self.assertTrue(report['census_changed_since_baseline'])
        self.assertEqual(report['review_required_container_ids'], members[1:])

    def test_baseline_scanner_missing_stops_before_inventory(self):
        report, calls = self.collect(census=[['d'*64]])
        self.assertEqual(calls, 0)
        self.assertEqual(report['failure']['code'], 'ownership-baseline-target-unavailable')

    def test_source_change_discards_workload_observation(self):
        report, _ = self.collect(pins=[{'test.py': 'a'*64}, {'test.py': 'b'*64}])
        self.assertNotIn('workloads', report)
        self.assertEqual(report['failure']['code'], 'ownership-source-changed')

    def test_only_exact_ids_are_inspected_in_bounded_batches(self):
        ids = [f'{v:064x}' for v in range(19)]
        def command(config, *args):
            self.assertEqual(args[:4], ('inspect', '--type', 'container', '--format'))
            self.assertEqual(args[4], o.FORMAT)
            self.assertLessEqual(len(args[5:]), 8)
            return b'\n'.join(json.dumps(workload(v)).encode() for v in args[5:])
        with patch.object(o.i, 'command', side_effect=command) as run:
            rows = o.inventory(Path('/unused'), ids)
        self.assertEqual(run.call_count, 3)
        self.assertEqual([v['id'] for v in rows], ids)
        for forbidden in ('.Config.Env', '.Config.Cmd', '.Config.Entrypoint', '{{json .}}'):
            self.assertNotIn(forbidden, o.FORMAT)

    def test_missing_labels_are_unknown_and_no_command_values_are_needed(self):
        row = workload(); row.update(project=None, service=None)
        with patch.object(o.i, 'command', return_value=json.dumps(row).encode()):
            self.assertEqual(o.inventory(Path('/unused'), ['a'*64]), [row])

    def test_foreign_duplicate_or_secret_bearing_fields_refuse(self):
        for rows in ([workload('c'*64)], [workload(), workload()],
                     [{**workload(), 'environment': ['SECRET']}],
                     [{**workload(), 'name': '/secret\nvalue'}]):
            data = b'\n'.join(json.dumps(v).encode() for v in rows)
            with self.subTest(rows=rows), patch.object(o.i, 'command', return_value=data), self.assertRaises(ValueError):
                o.inventory(Path('/unused'), ['a'*64])

    def test_inventory_error_does_not_export_raw_diagnostic_or_retry(self):
        baseline, sha = fixtures.encode(fixtures.fixture())
        with patch.object(o.i.host, 'trusted_local_docker'), patch.object(o, 'pins', return_value={}), \
             patch.object(o.r, 'census', return_value=['a'*64]), \
             patch.object(o, 'inventory', side_effect=RuntimeError('SECRET')) as run:
            report = o.collect(Path('/unused'), baseline, sha)
        self.assertEqual(run.call_count, 1)
        self.assertNotIn('SECRET', json.dumps(report))
        self.assertNotIn('workloads', report)

    def test_baseline_lookup_selects_exact_private_report_and_never_creates_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); results = root/'radar-r1-readiness-example/results'
            results.mkdir(parents=True, mode=0o700); path = results/'report.json'
            data, sha = fixtures.encode(fixtures.fixture()); path.write_bytes(data); path.chmod(0o600)
            before = list(root.rglob('*'))
            self.assertEqual(o.find_baseline(root, sha), data)
            self.assertEqual(list(root.rglob('*')), before)
            with self.assertRaises(ValueError): o.find_baseline(root, '0'*64)
            path.chmod(0o644)
            with self.assertRaises(ValueError): o.find_baseline(root, sha)

    def test_linked_report_is_never_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); data, sha = fixtures.encode(fixtures.fixture())
            target = root/'private.json'; target.write_bytes(data); target.chmod(0o600)
            results = root/'radar-r1-readiness-example/results'; results.mkdir(parents=True, mode=0o700)
            (results/'report.json').symlink_to(target)
            with self.assertRaises(ValueError): o.find_baseline(root, sha)

    def test_missing_baseline_cli_retains_private_failure_archive_without_host_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'results'
            with patch('sys.argv', ['ownership.py', '--baseline-root', tmp, '--baseline-sha256', '0'*64,
                                   '--output', str(out)]), patch.object(o, 'collect') as collect, \
                 redirect_stdout(io.StringIO()):
                old = os.umask(0o077)
                try: result = o.main()
                finally: os.umask(old)
            self.assertEqual(result, 1); collect.assert_not_called()
            report = json.loads((out/'report.json').read_bytes())
            self.assertEqual(report['failure']['code'], 'ownership-accepted-baseline-unavailable')
            self.assertFalse(report['observation_attempted'])
            with zipfile.ZipFile(out/'production-ownership.zip') as z:
                self.assertEqual(z.namelist(), ['report.json'])
                self.assertEqual(z.read('report.json'), (out/'report.json').read_bytes())
            self.assertEqual((out/'production-ownership.zip').stat().st_mode & 0o777, 0o600)


if __name__ == '__main__': unittest.main()
