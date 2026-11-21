"""New authority projection/collection tests; no Docker or host observation."""
from contextlib import contextmanager,redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import authority as a
import test_observed_target as fixture

DATA='/var/lib/docker/volumes/radar_data/_data'


def mount(source,destination='/mnt/fixture',rw=True,kind='bind',propagation='rprivate'):
    return {'type':kind,'source':source,'destination':destination,'rw':rw,'propagation':propagation}


def workload(identity='a'*64):
    return {'id':identity,'image':'sha256:'+'b'*64,'running':True,'pid':123,
        'started':'2026-11-01T00:00:00Z','privileged':False,'caps_add':None,'pid_mode':'',
        'network_mode':'bridge','mounts':[mount(DATA,'/app/data',kind='volume',propagation='')]}


class AuthorityTests(unittest.TestCase):
    def project(self,**changes):return a.project({**workload(),**changes},DATA)

    def test_socket_and_ancestor_exposure_are_flagged_even_if_declared_read_only(self):
        for source in ('/run/docker.sock','/var/run/docker.sock','/run','/var/run','/'):
            for writable in (True,False):
                row=self.project(mounts=[mount(source,rw=writable)])
                self.assertIn('local-docker-socket-path-exposed',row['findings'])
                self.assertNotIn(source,json.dumps(row))
        row=self.project(mounts=[mount('/run/user/1000/docker.sock')])
        self.assertIn('other-engine-socket-path-declared',row['findings'])

    def test_path_boundaries_and_relative_paths_do_not_create_false_matches(self):
        for source in ('/runtime','/run/docker.sock.backup','/var/run2','/var/lib/docker/volumes/radar_data/_database'):
            row=self.project(mounts=[mount(source)])
            self.assertEqual(row['findings'],[])
        for source in ('run/docker.sock','/run/../private','//run/docker.sock','/run//docker.sock','/run/docker.sock\nSECRET'):
            with self.assertRaises(ValueError):self.project(mounts=[mount(source)])

    def test_renamed_source_at_engine_socket_destination_remains_reviewable(self):
        row=self.project(mounts=[mount('/private/renamed-endpoint','/var/run/docker.sock',rw=False)])
        self.assertIn('engine-socket-destination-declared',row['findings'])
        self.assertNotIn('local-docker-socket-path-exposed',row['findings'])

    def test_data_parent_exact_and_child_mounts_are_reviewable_and_ro_is_distinct(self):
        for source in (DATA,DATA+'/radar.sqlite','/var/lib/docker/volumes','/'):
            row=self.project(mounts=[mount(source)])
            self.assertIn('scanner-data-write-path-declared',row['findings'])
            ro=self.project(mounts=[mount(source,rw=False)])
            self.assertIn('scanner-data-read-path-declared',ro['findings'])
            self.assertNotIn('scanner-data-write-path-declared',ro['findings'])

    def test_privileged_caps_namespace_and_propagation_flags_do_not_grant_authority(self):
        row=self.project(privileged=True,caps_add=['SYS_ADMIN'],pid_mode='host',network_mode='host',
                         mounts=[mount('/unrelated',propagation='rshared')])
        self.assertEqual(row['findings'],sorted(['privileged-container-declared','additional-capabilities-declared',
            'host-pid-namespace-declared','host-network-namespace-declared','propagating-mount-declared']))
        self.assertEqual(row['additional_capabilities_count'],1)
        self.assertNotIn('SYS_ADMIN',json.dumps(row))

    def test_mount_array_and_cap_order_are_semantically_stable_but_mutations_are_not(self):
        one=workload();one.update(caps_add=['SYS_ADMIN','SYS_PTRACE'],mounts=[mount(DATA),mount('/run/docker.sock','/engine')])
        two=copy.deepcopy(one);two['mounts'].reverse();two['caps_add'].reverse()
        self.assertEqual(a.validate(one),a.validate(two));self.assertEqual(a.project(one,DATA),a.project(two,DATA))
        two['mounts'][0]['rw']=False
        self.assertNotEqual(a.validate(one),a.validate(two))

    def test_no_raw_private_paths_or_namespace_or_cap_text_exported(self):
        row=self.project(caps_add=['SECRET_CANARY'],pid_mode='container:SECRET_CANARY',network_mode='SECRET_CANARY',
                         mounts=[mount('/private/SECRET_CANARY','/private/DESTINATION_CANARY')])
        serialized=json.dumps(row)
        self.assertNotIn('SECRET_CANARY',serialized);self.assertNotIn('DESTINATION_CANARY',serialized)
        self.assertEqual(row['mounts'][0]['source_sha256'],a.i.digest(b'/private/SECRET_CANARY'))

    def test_stopped_containers_remain_in_scope_and_malformed_metadata_is_rejected(self):
        row=workload();row.update(running=False,pid=0);self.assertFalse(a.validate(row)['running'])
        for changes in ({'pid':True},{'running':False},{'privileged':None},{'caps_add':'ALL'},
                        {'caps_add':['SYS_ADMIN','SYS_ADMIN']},{'pid_mode':None},
                        {'mounts':[mount('/a'),mount('/b')]},{'environment':['SECRET']},
                        {'mounts':[mount('/a',kind='unknown')]},{'mounts':[mount('/a')]*33}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):a.validate({**workload(),**changes})

    def test_omitted_optional_mount_fields_are_explicitly_unavailable(self):
        row=self.project(mounts=[mount(None,'/tmp',kind='tmpfs',propagation=None)])
        self.assertEqual(row['findings'],['mount-propagation-unavailable'])
        self.assertIsNone(row['mounts'][0]['propagation'])
        with self.assertRaises(ValueError):self.project(mounts=[mount(None,kind='bind')])

    def collect(self,*,rows=None,change=None,census_after=None,pin_after=None,error=None,clock=None):
        baseline,sha=fixture.encode(fixture.fixture());rows=copy.deepcopy(rows or [workload(),workload('d'*64)])
        ids=sorted(r['id'] for r in rows);calls=[];ps_count=0;inspect_count=0
        def command(config,*args):
            nonlocal ps_count,inspect_count
            calls.append(args)
            if error:raise error
            if args[0]=='ps':
                self.assertEqual(args,('ps','--all','--no-trunc','--format','{{.ID}}'));ps_count+=1
                return ('\n'.join(census_after if ps_count==2 and census_after is not None else ids)+'\n').encode()
            self.assertEqual(args[:5],('inspect','--type','container','--format',a.FORMAT))
            self.assertLessEqual(len(args[5:]),a.CHUNK);inspect_count+=1
            selected=copy.deepcopy([r for r in rows if r['id'] in args[5:]])
            if change and inspect_count>(len(ids)+a.CHUNK-1)//a.CHUNK:change(selected)
            return b'\n'.join(a.i.raw(row).strip() for row in selected)
        with patch.object(a.i.host,'trusted_local_docker'),patch.object(a.i,'command',side_effect=command),\
             patch.object(a,'pins',side_effect=[{'x.py':'a'*64},pin_after or {'x.py':'a'*64}]):
            report=a.collect(Path('/unused'),baseline,sha,**({'clock':clock} if clock else {}))
        return report,calls

    def test_complete_pass_is_redacted_metadata_review_not_sole_owner_proof(self):
        other=workload('d'*64);other.update(running=False,pid=0,mounts=[mount('/var/run/docker.sock',rw=False)])
        unknown=workload('e'*64);unknown['mounts']=[]
        report,calls=self.collect(rows=[workload(),other,unknown])
        self.assertEqual(report['status'],'docker-authority-observed-review-pending')
        self.assertEqual(len(calls),6);self.assertEqual(report['docker_requests_attempted'],6)
        self.assertEqual(report['review_required_container_ids'],['d'*64])
        self.assertEqual(report['unclassified_container_ids'],['e'*64])
        self.assertEqual(report['running_container_count'],2)
        self.assertTrue(all(stage['status']=='completed' for stage in report['stages']))
        for key in a.FLAGS:self.assertIs(report[key],False)
        for forbidden in ('.Config.Env','.Config.Cmd','.Config.Entrypoint','{{json .}}'):
            self.assertNotIn(forbidden,a.FORMAT)
        self.assertNotIn('/var/run/docker.sock',json.dumps(report))

    def test_reordered_mounts_do_not_create_a_spurious_drift_failure(self):
        row=workload();row['mounts'].append(mount('/unrelated'))
        report,_=self.collect(rows=[row],change=lambda rs:rs[0]['mounts'].reverse())
        self.assertEqual(report['status'],'docker-authority-observed-review-pending')

    def test_changed_generation_mounts_or_census_discard_partial_metadata_without_retry(self):
        for change in (lambda rows:rows[0].update(pid=124),lambda rows:rows[0]['mounts'][0].update(rw=False)):
            report,calls=self.collect(change=change)
            self.assertEqual(len(calls),3);self.assertEqual(report['failure']['code'],'authority-metadata-changed')
            self.assertNotIn('workloads',report)
            self.assertEqual(report['stages'][7]['status'],'not-run')
        report,calls=self.collect(census_after=['a'*64])
        self.assertEqual(len(calls),4);self.assertNotIn('workloads',report)
        self.assertEqual(report['failure']['code'],'authority-census-changed')

    def test_wrong_baseline_target_stops_before_a_second_metadata_pass(self):
        for changes,code in (({'pid':124},'authority-target-generation-drift'),
                             ({'mounts':[mount('/other','/app/data',kind='volume')]},'authority-target-data-mount-drift')):
            report,calls=self.collect(rows=[{**workload(),**changes}])
            self.assertEqual(len(calls),2);self.assertEqual(report['failure']['code'],code)
            self.assertNotIn('workloads',report)
        report,calls=self.collect(rows=[workload('d'*64)])
        self.assertEqual(len(calls),1);self.assertEqual(report['failure']['code'],'authority-target-missing')

    def test_source_drift_or_command_failure_cannot_export_success_or_raw_errors(self):
        report,_=self.collect(pin_after={'x.py':'b'*64})
        self.assertEqual(report['failure']['code'],'authority-source-changed');self.assertNotIn('workloads',report)
        class SecretError(Exception):
            def __str__(self):raise AssertionError('must not format raw errors')
        report,calls=self.collect(error=SecretError('SECRET_CANARY'))
        self.assertEqual(len(calls),1);self.assertNotIn('SECRET_CANARY',json.dumps(report))
        self.assertNotIn('workloads',report)

    def test_expiry_prevents_another_request_and_no_retry_occurs(self):
        times=iter((0,0,90))
        report,calls=self.collect(clock=lambda:next(times))
        self.assertEqual(len(calls),1);self.assertEqual(report['failure']['code'],'authority-total-deadline')
        self.assertNotIn('workloads',report)

    def test_clock_regression_nonfinite_or_boolean_cannot_complete_observation(self):
        for value in (-1,float('nan'),float('inf'),True):
            times=iter((0,value))
            report,calls=self.collect(clock=lambda:next(times))
            self.assertEqual(calls,[]);self.assertEqual(report['failure']['code'],'authority-total-deadline')

    def test_foreign_duplicate_or_oversized_census_and_inspect_responses_refuse(self):
        for ids in ([],['a'*64]*2,['x'],[f'{n:064x}' for n in range(65)]):
            with self.assertRaises(ValueError):a.census(lambda *_:('\n'.join(ids)+'\n').encode())
        for rows in ([workload('d'*64)],[workload(),workload()], [{**workload(),'extra':'SECRET'}]):
            with self.assertRaises(ValueError):a.inventory(lambda *_:b'\n'.join(a.i.raw(r) for r in rows),['a'*64])

    def test_full_bound_uses_only_fixed_ps_and_inspect_requests(self):
        rows=[workload(f'{n:064x}') for n in range(63)]+[workload()]
        report,calls=self.collect(rows=rows)
        self.assertEqual(report['status'],'docker-authority-observed-review-pending')
        self.assertEqual(len(calls),66)
        self.assertEqual({args[0] for args in calls},{'ps','inspect'})

    def test_missing_baseline_writes_only_failure_report_and_never_observes_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'results';before=os.umask(0o077)
            try:
                with patch.object(a,'collect',side_effect=AssertionError('host')),redirect_stdout(io.StringIO()):
                    code=a.main(['--baseline-root',tmp,'--baseline-sha256','0'*64,'--output',str(out)])
            finally:os.umask(before)
            self.assertEqual(code,1);report=json.loads((out/'report.json').read_bytes())
            self.assertFalse(report['observation_attempted']);self.assertEqual(report['docker_requests_attempted'],0)
            with zipfile.ZipFile(out/'production-authority.zip') as z:
                self.assertEqual(z.namelist(),['report.json']);self.assertEqual(z.read('report.json'),(out/'report.json').read_bytes())
            self.assertEqual((out/'report.json').stat().st_mode&0o777,0o600)
            with self.assertRaisesRegex(ValueError,'authority-output-exists'):
                a.main(['--baseline-root',tmp,'--baseline-sha256','0'*64,'--output',str(out)])

    def test_local_cleanup_failure_does_not_erase_a_performed_observation(self):
        observed,_=self.collect();baseline,sha=fixture.encode(fixture.fixture())
        @contextmanager
        def config(**_):
            yield '/unused'
            raise OSError('SECRET_DIAGNOSTIC')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'results';before=os.umask(0o077)
            try:
                with patch.object(a.o,'find_baseline',return_value=baseline),\
                     patch.object(a,'collect',return_value=observed),\
                     patch.object(a.tempfile,'TemporaryDirectory',side_effect=config),\
                     patch.object(a.i.host,'write_report',side_effect=lambda path,row:path.write_bytes(a.i.raw(row))),\
                     redirect_stdout(io.StringIO()):
                    result=a.main(['--baseline-root',tmp,'--baseline-sha256',sha,'--output',str(out)])
            finally:os.umask(before)
            row=json.loads((out/'report.json').read_bytes());self.assertEqual(result,1)
            self.assertTrue(row['observation_attempted']);self.assertEqual(row['docker_requests_attempted'],4)
            self.assertEqual(row['failure']['stage'],'private-client-configuration-cleanup')
            self.assertNotIn('workloads',row);self.assertNotIn('SECRET_DIAGNOSTIC',json.dumps(row))


if __name__=='__main__':unittest.main()
