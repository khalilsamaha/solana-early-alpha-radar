import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import manifest as m


def inputs():
    config = {k: None for k in m.CONFIG}
    policy = {k: None for k in m.POLICY}
    return config, policy


class ManifestTests(unittest.TestCase):
    def test_missing_inputs_remain_blocked(self):
        config, policy = inputs(); row = m.build(config, policy)
        self.assertIsNone(row['capacity'])
        self.assertEqual(len([b for b in row['blockers'] if b.startswith('missing:')]), len(config)+len(policy))
        self.assertFalse(row['activation_authorized'])

    def test_complete_inputs_cannot_create_authority(self):
        config, policy = inputs()
        for k in config:
            config[k] = 'a'*64 if k.endswith('_sha256') else None
        config.update(scanner_image='sha256:'+'b'*64, registry_path='/var/lib/radar-control',
                      endpoint_path='/var/lib/radar-control/discovery.sock', capture_path='/var/lib/radar-capture', credential_method='sealed-fd')
        policy.update({k: 1 for k in policy})
        row = m.build(config, policy)
        self.assertFalse(any(b.startswith('missing:') for b in row['blockers']))
        self.assertIn('exact-pilot-and-rollout-approval-required', row['blockers'])
        self.assertFalse(row['activation_authorized'])
        self.assertFalse(row['capacity']['space_reserved'])

    def test_capacity_accounts_for_quarantine_and_staging(self):
        config, p = inputs()
        p.update(raw_bytes=100, database_bytes=200, journal_bytes=300, receipt_bytes=400,
                 retained_runs=2, quarantined_runs=3, headroom_bytes=1000)
        row=m.build(config,p)['capacity']; source=100+400+4096+300+400; envelope=source+65536
        self.assertEqual(row['required_free_bytes'],5*(source+envelope)+2*source+3*envelope+1000)
        p['quarantined_runs']=4
        self.assertEqual(m.build(config,p)['capacity']['required_free_bytes']-row['required_free_bytes'],source+envelope)

    def test_numeric_types_and_draft_ceilings(self):
        for key,value in [('raw_bytes',True),('raw_bytes',8*1024**2+1),('research_seconds',172801),
                          ('shutdown_seconds',31),('retained_runs',0),('memory_bytes',1.5),('funding_lamports',-1)]:
            with self.subTest(key=key,value=value):
                config,p=inputs();p[key]=value
                with self.assertRaises(ValueError):m.build(config,p)

    def test_capacity_overflow_refuses(self):
        config,p=inputs()
        p.update({k:2**53-1 for k in ('database_bytes','journal_bytes','receipt_bytes','retained_runs','quarantined_runs','headroom_bytes')})
        p['raw_bytes']=1
        with self.assertRaisesRegex(ValueError,'capacity-overflow'):m.build(config,p)

    def test_service_lifetime_and_paths(self):
        config,p=inputs();p.update(research_seconds=20,service_seconds=10)
        with self.assertRaisesRegex(ValueError,'service-lifetime'):m.build(config,p)
        p['service_seconds']=20
        for path in ('relative','/a/../b','/a//b','/a\n'):
            config['capture_path']=path
            with self.assertRaises(ValueError):m.build(config,p)
        config.update(capture_path='/a/child',registry_path='/a',endpoint_path='/a/discovery.sock')
        with self.assertRaisesRegex(ValueError,'path-overlap'):m.build(config,p)
        config.update(capture_path='/b',endpoint_path='/other/discovery.sock')
        with self.assertRaisesRegex(ValueError,'endpoint-binding'):m.build(config,p)

    def test_no_secret_or_unknown_fields(self):
        config,p=inputs();config['credential']='secret'
        with self.assertRaisesRegex(ValueError,'config-fields'):m.build(config,p)
        del config['credential'];config['credential_method']='environment'
        with self.assertRaisesRegex(ValueError,'credential-method'):m.build(config,p)
        config['credential_method']=None;config['remote_destination_sha256']='https://secret'
        with self.assertRaisesRegex(ValueError,'config-hash'):m.build(config,p)

    def test_builder_copies_inputs(self):
        config,p=inputs();row=m.build(config,p);p['service_seconds']=5
        self.assertIsNone(row['policy']['service_seconds'])

    def test_freeze_and_byte_preserving_inspection(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'plan';row=m.build(*inputs());sha=m.freeze(path,row)
            before=(path/'manifest.json').read_bytes()
            self.assertEqual(m.inspect(path,sha),row)
            self.assertEqual((path/'manifest.json').read_bytes(),before)
            with self.assertRaises(FileExistsError):m.freeze(path,row)

    def test_tamper_wrong_digest_and_source_drift_refuse(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'plan';row=m.build(*inputs());sha=m.freeze(path,row)
            with self.assertRaisesRegex(ValueError,'manifest-digest'):m.inspect(path,'0'*64)
            with patch.object(m,'sources',return_value={'changed':'0'*64}):
                with self.assertRaisesRegex(ValueError,'manifest-binding'):m.inspect(path,sha)
            edited=copy.deepcopy(row);edited['activation_authorized']=True
            (path/'manifest.json').write_bytes(m.raw(edited))
            with self.assertRaisesRegex(ValueError,'manifest-binding'):m.inspect(path,m.digest(m.raw(edited)))

    def test_links_and_permissions_refuse(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'plan';row=m.build(*inputs());sha=m.freeze(path,row)
            file=path/'manifest.json';file.chmod(0o644)
            with self.assertRaisesRegex(ValueError,'private-manifest'):m.inspect(path,sha)
            file.chmod(0o600);os.link(file,Path(d)/'hardlink')
            with self.assertRaisesRegex(ValueError,'private-manifest'):m.inspect(path,sha)
            alias=Path(d)/'alias';alias.symlink_to(path,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'path-link'):m.inspect(alias,sha)

    def test_failed_durability_consumes_directory(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'plan';row=m.build(*inputs())
            with patch.object(m.os,'fsync',side_effect=OSError('fixture')):
                with self.assertRaises(OSError):m.freeze(path,row)
            self.assertTrue(path.exists())
            with self.assertRaises(FileExistsError):m.freeze(path,row)

    def test_duplicate_and_nonfinite_json_refuse(self):
        for data in (b'{"a":1,"a":2}',b'{"a":NaN}'):
            with self.assertRaises(ValueError):m.parse(data)


if __name__=='__main__':unittest.main()
