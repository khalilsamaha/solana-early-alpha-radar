import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import intake as i
import check_intake as c


class ReportTests(unittest.TestCase):
    def test_offline_mode_never_attempts_observation(self):
        with patch.object(i,'observe',side_effect=AssertionError('host')):
            row=c.collect(Path('/empty'),offline=True)
        self.assertFalse(row['observation_attempted']);self.assertIsNone(row['observation'])
        self.assertEqual(row['status'],'production-context-offline-tests-only')

    def test_daemon_diagnostic_is_never_retained(self):
        for error in (OSError('private-credential-like-detail'),ValueError('private-credential-like-detail')):
            with patch.object(i,'observe',side_effect=error):row=c.collect(Path('/empty'),offline=False)
            self.assertTrue(row['observation_attempted']);self.assertIsNone(row['observation'])
            self.assertEqual(row['error'],'observation-unavailable')
            self.assertNotIn('private-credential',json.dumps(row))

    def test_known_error_and_source_change_are_explicitly_unavailable(self):
        with patch.object(i,'observe',side_effect=i.host.ReviewError('container-or-process-changed')):
            row=c.collect(Path('/empty'),offline=False)
        self.assertEqual(row['error'],'container-or-process-changed')
        with patch.object(i,'pins',side_effect=[{'a':'b'},{}]):row=c.collect(Path('/empty'),offline=True)
        self.assertEqual(row['error'],'context-source-changed');self.assertIsNone(row['observation'])

    def test_observed_metadata_cannot_grant_authority(self):
        with patch.object(i,'observe',return_value={'bounded-test-observation':True}):
            row=c.collect(Path('/empty'),offline=False)
        self.assertEqual(row['status'],'production-context-observed-rollout-blocked')
        for key in ('activation_authorized','automatic_resume_allowed','full_gate_accepted','production_modified',
                    'environment_read','argv_read','credentials_exported','provider_connection_opened'):
            self.assertIs(row[key],False)

    def test_private_report_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'report.json';i.host.write_report(path,{'proof':'first'})
            before=path.read_bytes();self.assertEqual(path.stat().st_mode&0o777,0o600)
            with self.assertRaises(FileExistsError):i.host.write_report(path,{'proof':'second'})
            self.assertEqual(path.read_bytes(),before)


if __name__=='__main__':unittest.main()
