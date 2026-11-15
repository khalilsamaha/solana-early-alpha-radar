import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import intake as i


def target():
    return {'id':'a'*64,'image':'sha256:'+'b'*64,'name':'/'+i.host.TARGET,'pid':123,'running':True,
      'started':'2026-11-15T19:00:00.000000000Z','user':'1000:1000','working_dir':'/app',
      'project':i.PROJECT,'service':i.SERVICE,'readonly_rootfs':True,'privileged':False,'init':True,
      'restart_policy':'unless-stopped','memory':134217728,'memory_swap':134217728,'nano_cpus':1000000000,
      'pids_limit':32,'network_mode':'radar_default',
      'mounts':[{'type':'volume','source':'/var/lib/docker/volumes/radar_data/_data','destination':'/app/data','rw':True}]}


class IntakeTests(unittest.TestCase):
    def observe(self,rows=None,members=None,identity=None):
        row=target();rows=rows or [row,copy.deepcopy(row)];members=members or [['a'*64],['a'*64]]
        identity=identity or {'container':row,'findings':[],'same_uid_and_namespace_observed':True}
        with patch.object(i.host,'trusted_local_docker'),patch.object(i,'metadata',side_effect=rows),\
             patch.object(i,'census',side_effect=members),patch.object(i.host,'observe',return_value=identity):
            return i.observe(Path('/fixture/empty-config'))

    def test_stable_projection_is_observation_never_owner_or_rollout_authority(self):
        row=self.observe();self.assertEqual(row['metadata_sha256'],i.digest(i.raw(target())))
        self.assertEqual(row['project_running_container_count'],1)
        for key in ('sole_owner_verified','full_configuration_verified','production_ipc_peer_verified',
                    'environment_read','argv_read','production_modified','activation_authorized','automatic_resume_allowed'):
            self.assertIs(row[key],False)

    def test_extra_project_member_is_retained_without_sole_owner_claim(self):
        row=self.observe(members=[['a'*64,'c'*64],['a'*64,'c'*64]])
        self.assertEqual(row['project_running_container_count'],2);self.assertFalse(row['sole_owner_verified'])

    def test_changed_target_or_membership_refuses(self):
        changed={**target(),'pid':124}
        with self.assertRaisesRegex(ValueError,'context-changed'):self.observe(rows=[target(),changed])
        with self.assertRaisesRegex(ValueError,'context-changed'):self.observe(members=[['a'*64],['a'*64,'c'*64]])

    def test_identity_disagreement_or_absent_target_refuses(self):
        with self.assertRaisesRegex(ValueError,'context-process-binding'):
            self.observe(identity={'container':{**target(),'image':'sha256:'+'c'*64}})
        with self.assertRaisesRegex(ValueError,'context-target-outside-census'):
            self.observe(members=[['c'*64],['c'*64]])

    def test_metadata_rejects_unknown_secret_fields_and_numeric_booleans(self):
        for changed in ({**target(),'environment':['secret-value']},{**target(),'pid':True},
                        {**target(),'memory':True},{**target(),'privileged':0},{**target(),'pids_limit':1.5}):
            with self.assertRaises(ValueError):i.validate(changed)

    def test_metadata_rejects_wrong_project_service_and_target(self):
        for key in ('project','service','name'):
            with self.subTest(key=key),self.assertRaises(ValueError):i.validate({**target(),key:'other'})

    def test_mount_bounds_links_control_text_and_duplicate_destinations(self):
        for mount in ({'type':'volume','source':'relative','destination':'/app/data','rw':True},
                      {'type':'bind','source':'/secret\nvalue','destination':'/app/data','rw':True},
                      {'type':'bind','source':'/a/../b','destination':'/app/data','rw':True}):
            with self.assertRaises(ValueError):i.validate({**target(),'mounts':[mount]})
        with self.assertRaises(ValueError):i.validate({**target(),'mounts':target()['mounts']*2})
        with self.assertRaises(ValueError):i.validate({**target(),'mounts':target()['mounts']*17})

    def test_zero_unlimited_limits_are_evidence_not_adequacy(self):
        row={**target(),'memory':0,'memory_swap':-1,'pids_limit':None,'nano_cpus':0}
        self.assertEqual(i.validate(row),row)

    def test_metadata_request_uses_only_fixed_read_only_projection(self):
        with patch.object(i.host,'bounded_command',return_value=i.raw(target())) as run:
            self.assertEqual(i.metadata(Path('/empty')),target())
        command=run.call_args.args[0]
        self.assertEqual(command[:5],[i.host.DOCKER,'--config','/empty','--host','unix://'+i.host.SOCKET])
        self.assertEqual(command[5:9],['inspect','--type','container','--format'])
        self.assertEqual(command[-1],i.host.TARGET)
        for forbidden in ('.Config.Env','.Config.Cmd','.Args','.Path','.NetworkSettings'):
            self.assertNotIn(forbidden,i.FORMAT)

    def test_census_is_project_scoped_and_bounded(self):
        with patch.object(i.host,'bounded_command',return_value=('c'*64+'\n'+'a'*64+'\n').encode()) as run:
            self.assertEqual(i.census(Path('/empty')),['a'*64,'c'*64])
        self.assertEqual(run.call_args.args[0][5:],['ps','--no-trunc','--filter',
            'label=com.docker.compose.project='+i.PROJECT,'--format','{{.ID}}'])
        for raw in (b'not-an-id\n',('a'*64+'\n'+'a'*64+'\n').encode(),b'\xff'):
            with patch.object(i.host,'bounded_command',return_value=raw),self.assertRaises((ValueError,UnicodeError)):
                i.census(Path('/empty'))

    def test_source_drift_refuses(self):
        original=i.pins();row=target()
        with patch.object(i,'pins',side_effect=[original,{}]),patch.object(i.host,'trusted_local_docker'),\
             patch.object(i,'metadata',return_value=row),patch.object(i,'census',return_value=['a'*64]),\
             patch.object(i.host,'observe',return_value={'container':row}):
            with self.assertRaisesRegex(ValueError,'context-source-changed'):i.observe(Path('/empty'))


if __name__=='__main__':unittest.main()
