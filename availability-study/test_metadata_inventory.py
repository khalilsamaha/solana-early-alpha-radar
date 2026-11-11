import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import metadata_inventory as m


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old, self.new, self.live, self.backup = [self.root/n for n in ('old', 'new', 'live', 'backup')]
        for p in (self.old, self.new, self.live, self.backup):
            p.mkdir(mode=0o700)
        frozen = 1700000000000
        embargo = m.FORWARD_PROTOCOL['holdout']['embargoMs']
        self.model = {'format': 'forward-model-1', 'protocol': m.FORWARD_PROTOCOL,
                      'protocolSha256': m.digest(m.FORWARD_PROTOCOL), 'modelFrozen': True,
                      'liveUseAllowed': False, 'sourceIdentity': 'private-source-marker',
                      'frozenAt': frozen, 'trainingCutoffAt': frozen-embargo,
                      'testNotBeforeAt': frozen+embargo, 'seenTrainingMints': ['private-training-token'],
                      'groups': [{'cohort': 'early-activity', 'target': 'exitQuoteAvailable',
                                  'models': {'legacy': {'private-coefficient-marker': [1, 2]}}}]}
        pin = m.digest(self.model)
        self.patcher = patch.object(m, 'ARTIFACT_PIN', pin)
        self.patcher.start(); self.addCleanup(self.patcher.stop)
        self.original = {'format': 'frozen-forward-experiment-1', 'artifactSha256': pin,
                         'sourceIdentity': self.model['sourceIdentity'], 'liveUseAllowed': False,
                         'installedAt': frozen+1000, 'testNotBeforeAt': frozen+1000+embargo}
        registered = frozen+3*m.DAY
        start = ((registered+m.PROTOCOL['maturityMs'])//m.DAY+1)*m.DAY
        self.reg = {'format': 'availability-confirmation-1', 'protocol': m.PROTOCOL,
                    'protocolSha256': m.digest(m.PROTOCOL), 'artifactSha256': pin,
                    'modelSha256': m.digest(self.model['groups'][0]['models']['legacy']),
                    'sourceIdentity': self.model['sourceIdentity'], 'reviewedReportSha256': m.REVIEW_PIN,
                    'diagnosticSha256': m.DIAGNOSTIC_PIN, 'liveUseAllowed': False,
                    'registeredAt': registered, 'developmentCutoffAt': frozen+2*m.DAY,
                    'startAt': start, 'endAt': start+7*m.DAY,
                    'reviewNotBeforeAt': start+7*m.DAY+m.PROTOCOL['maturityMs'],
                    'excludedMints': ['private-development-token', 'private-training-token']}
        self.reg['excludedMintsSha256'] = m.digest(self.reg['excludedMints'])
        self.now = self.reg['reviewNotBeforeAt']+m.DAY
        self.write_registrations()
        self.captures = []
        for root, a, b in ((self.old, self.original['testNotBeforeAt'], self.reg['developmentCutoffAt']),
                           (self.new, self.reg['startAt'], self.reg['endAt'])):
            (root/'captures').mkdir(mode=0o700)
            p=root/'captures/capture-one';p.mkdir(mode=0o700)
            self.capture(p, a, b);self.captures.append(p)
        for p in (self.live, self.backup):self.capture(p, self.reg['startAt'], self.reg['endAt'])
        self.pins = patch.dict(m.CAPTURE_PINS, {
            role: hashlib.sha256(gzip.decompress((path/'capture-index.json.gz').read_bytes())).hexdigest()
            for role, path in (('b0-live', self.live), ('b0-backup', self.backup))})
        self.pins.start();self.addCleanup(self.pins.stop)

    def sha(self, path):return hashlib.sha256(path.read_bytes()).hexdigest()

    def write(self, path, value):
        path.write_bytes(gzip.compress(json.dumps(value).encode(),mtime=0));path.chmod(0o600)

    def write_registrations(self):
        for root in (self.old, self.new):self.write(root/'model.json.gz',dict(self.model,artifactSha256=m.digest(self.model)))
        self.write(self.old/'experiment.json.gz',dict(self.original,registrationSha256=m.digest(self.original)))
        self.write(self.new/'registration.json.gz',dict(self.reg,registrationSha256=m.digest(self.reg)))

    def capture(self, path, a, b):
        # Deliberately not gzip/JSON: byte verification must never decode outcomes.
        part=path/'part-00.json.gz';part.write_bytes(b'opaque-outcome-payload-must-not-be-decoded');part.chmod(0o600)
        self.write(path/'capture-index.json.gz',{'format':'quote-history-capture-1','complete':True,
            'windowClock':'observer-detected-time','sourceIdentity':self.model['sourceIdentity'],
            'requestedStartAt':a,'entryWindowEndAt':b,'capturedAt':self.reg['reviewNotBeforeAt'],
            'chunks':[{'file':part.name,'sha256':self.sha(part),'startAt':a,'endAt':b}]})

    def run_inventory(self):
        return m.inventory(self.old,self.new,self.live,self.backup)

    def test_complete_metadata_stays_blocked_private_and_preserves_sources(self):
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        r=self.run_inventory()
        self.assertEqual(r['state'],'inventory-complete-readiness-blocked');self.assertEqual(r['errors'],[])
        self.assertEqual(r['identities']['trainingTokens']['count'],1)
        self.assertEqual(r['identities']['trainingAndDevelopmentTokens']['count'],2)
        self.assertEqual(len(r['captures']),4)
        for v in r['captures'].values():
            self.assertTrue(v['chunkBytesVerified']);self.assertFalse(v['chunkPayloadsDecoded'])
            self.assertFalse(v['fullReplayVerified']);self.assertFalse(v['tokenMembershipExtracted'])
        for k in ('modelEvaluated','modelTrained','studyRegistered','gatePassed','liveUseAllowed',
                  'offMachineRestoreVerified','futureExclusionRegistryComplete','outcomePayloadsDecoded'):
            self.assertFalse(r[k])
        raw=json.dumps(r)
        for value in ('private-source-marker','private-training-token','private-development-token','private-coefficient-marker'):
            self.assertNotIn(value,raw)
        for path,raw in before.items():self.assertEqual(path.read_bytes(),raw)

    def test_model_pin_cannot_be_replaced_by_resealing(self):
        changed=copy.deepcopy(self.model);changed['groups'][0]['models']['legacy']['private-coefficient-marker']=[9]
        self.write(self.new/'model.json.gz',dict(changed,artifactSha256=m.digest(changed)))
        r=self.run_inventory();self.assertEqual(r['state'],'inventory-partial-readiness-blocked')
        self.assertIsNone(r['identities']);self.assertIn('frozen-model-identity',[e['code'] for e in r['errors']])

    def test_registration_links_and_closed_clocks_refuse_resealed_changes(self):
        for key,value in [('modelSha256','a'*64),('reviewedReportSha256','a'*64),('diagnosticSha256','a'*64),
                          ('endAt',self.reg['endAt']+1),('liveUseAllowed',True)]:
            with self.subTest(key=key):
                reg=dict(self.reg);reg[key]=value
                self.write(self.new/'registration.json.gz',dict(reg,registrationSha256=m.digest(reg)))
                self.assertIsNone(self.run_inventory()['identities'])
        self.write_registrations()

    def test_exclusions_cannot_lose_training_tokens(self):
        self.reg['excludedMints']=['private-development-token']
        self.reg['excludedMintsSha256']=m.digest(self.reg['excludedMints']);self.write_registrations()
        self.assertIsNone(self.run_inventory()['identities'])

    def test_original_registration_cannot_change_source_or_install_boundary(self):
        for key,value in [('sourceIdentity','other'),('artifactSha256','a'*64),
                          ('testNotBeforeAt',self.original['testNotBeforeAt']-1),('liveUseAllowed',True)]:
            with self.subTest(key=key):
                old=dict(self.original);old[key]=value
                self.write(self.old/'experiment.json.gz',dict(old,registrationSha256=m.digest(old)))
                self.assertIsNone(self.run_inventory()['identities'])

    def test_manifest_traversal_clock_source_and_noncontiguous_chunks_fail(self):
        p=self.captures[0]/'capture-index.json.gz'
        original=json.loads(gzip.decompress(p.read_bytes()))
        mutators=[lambda x:x['chunks'][0].update(file='../private.json.gz'),
                  lambda x:x['chunks'][0].update(startAt=x['requestedStartAt']+1),
                  lambda x:x.update(capturedAt=10**15),lambda x:x.update(sourceIdentity='other'),
                  lambda x:x.update(complete=False)]
        for mutate in mutators:
            x=copy.deepcopy(original);mutate(x);self.write(p,x)
            self.assertIsNone(self.run_inventory()['captures']['original-00'])

    def test_missing_roots_report_partial_without_creating_them(self):
        missing=self.root/'absent'
        r=m.inventory(missing,self.new,self.live,self.backup)
        self.assertEqual(r['state'],'inventory-partial-readiness-blocked');self.assertFalse(missing.exists())
        self.assertNotIn(str(missing),json.dumps(r))

    def test_chunk_tampering_is_reported_and_never_repaired(self):
        path=self.captures[1]/'part-00.json.gz';path.write_bytes(b'changed')
        r=self.run_inventory();self.assertIsNone(r['captures']['confirmation-00'])
        self.assertIn('chunk-checksum',[e['code'] for e in r['errors']]);self.assertEqual(path.read_bytes(),b'changed')

    def test_pinned_b0_index_cannot_be_substituted(self):
        self.capture(self.live,self.reg['startAt']+1,self.reg['endAt'])
        r=self.run_inventory();self.assertIsNone(r['captures']['b0-live'])
        self.assertIn('pinned-index-mismatch',[e['code'] for e in r['errors']])

    def test_b0_pin_matches_historical_reader_contract(self):
        # Exercise the existing reader used by history.load_capture, independently
        # of the new metadata reader and the fixture pin calculation.
        path=self.live/'capture-index.json.gz'
        code='import sys; sys.path.insert(0,sys.argv[1]); from pathlib import Path; from build import read; print(read(Path(sys.argv[2]))[1]["sha256"])'
        result=subprocess.run([sys.executable,'-E','-s','-S','-B','-c',code,
                               str(m.ROOT/'research-dataset'),str(path)],
                              text=True,capture_output=True,check=True)
        with patch.dict(m.CAPTURE_PINS, {'b0-live':result.stdout.strip()}):
            r=self.run_inventory()
        self.assertEqual(r['errors'],[])
        item=r['captures']['b0-live']
        self.assertEqual(item['decodedSha256'],result.stdout.strip())
        self.assertEqual(item['compressedSha256'],self.sha(path))
        self.assertNotEqual(item['decodedSha256'],item['compressedSha256'])

    def test_b0_gzip_header_change_preserves_exact_decoded_identity(self):
        path=self.live/'capture-index.json.gz'
        raw=gzip.decompress(path.read_bytes());before=self.sha(path)
        path.write_bytes(gzip.compress(raw,mtime=1))
        r=self.run_inventory()
        self.assertEqual(r['errors'],[])
        self.assertNotEqual(before,r['captures']['b0-live']['compressedSha256'])
        self.assertEqual(r['captures']['b0-live']['decodedSha256'],m.CAPTURE_PINS['b0-live'])
        # Chunk identities remain compressed-byte identities.
        (self.live/'part-00.json.gz').write_bytes(b'changed')
        self.assertIn({'scope':'b0-live','code':'chunk-checksum'},self.run_inventory()['errors'])

    def test_b0_equivalent_json_reserialization_does_not_satisfy_pin(self):
        path=self.live/'capture-index.json.gz'
        raw=gzip.decompress(path.read_bytes())
        path.write_bytes(gzip.compress(raw+b'\n',mtime=0))
        self.assertEqual(json.loads(raw),json.loads(gzip.decompress(path.read_bytes())))
        self.assertIn({'scope':'b0-live','code':'pinned-index-mismatch'},self.run_inventory()['errors'])

    def test_symlink_parent_and_hardlink_are_rejected(self):
        alias=self.root/'alias';alias.symlink_to(self.old,target_is_directory=True)
        with self.assertRaisesRegex(m.InventoryError,'symlink-path'):m.Reader().metadata(alias/'model.json.gz',8*m.MIB)
        os.link(self.old/'model.json.gz',self.root/'hardlink')
        with self.assertRaisesRegex(m.InventoryError,'input-type-or-link'):m.Reader().metadata(self.old/'model.json.gz',8*m.MIB)

    def test_private_permission_mismatch_fails(self):
        (self.new/'model.json.gz').chmod(0o644)
        self.assertIn('private-permissions',[e['code'] for e in self.run_inventory()['errors']])

    def test_duplicate_keys_and_gzip_bomb_are_rejected(self):
        path=self.root/'metadata.gz';path.write_bytes(gzip.compress(b'{"x":1,"x":2}'))
        with self.assertRaisesRegex(m.InventoryError,'duplicate-json-key'):m.Reader().metadata(path,100)
        path.write_bytes(gzip.compress(b' '*10000))
        with self.assertRaisesRegex(m.InventoryError,'decoded-byte-cap'):m.Reader().metadata(path,100)

    def test_directory_and_byte_deadline_budgets_fail_closed(self):
        for n in range(33):(self.old/'captures'/str(n)).touch()
        with self.assertRaisesRegex(m.InventoryError,'directory-entry-cap'):m.capture_directories(m.Reader(),self.old)
        reader=m.Reader();reader.bytes=512*m.MIB+1
        with self.assertRaisesRegex(m.InventoryError,'total-byte-cap'):reader.guard()
        reader=m.Reader();reader.deadline=0
        with self.assertRaisesRegex(m.InventoryError,'read-deadline'):reader.guard()

    def test_final_check_detects_changed_source(self):
        reader=m.Reader();path=self.old/'model.json.gz';reader.metadata(path,8*m.MIB)
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(m.InventoryError,'source-changed'):reader.finish()

    def test_requested_windows_include_leading_internal_and_trailing_gaps(self):
        rows={'confirmation-0':{'requestedWindow':[20,40],'capturedAt':200},
              'confirmation-1':{'requestedWindow':[50,80],'capturedAt':200},
              'confirmation-2':{'requestedWindow':[70,90],'capturedAt':200}}
        r=m.window_inventory(rows,'confirmation',[10,100])
        self.assertEqual(r['uncoveredRequestedIntervals'],[[10,20],[40,50],[90,100]])
        self.assertFalse(r['requestedWindowCovered']);self.assertFalse(r['continuousUptimeVerified'])

    def test_output_is_private_atomic_and_never_replaced(self):
        path=self.root/'result.gz';r=self.run_inventory();m.publish(path,r)
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        self.assertEqual(json.loads(gzip.decompress(path.read_bytes())),r)
        before=path.read_bytes()
        with self.assertRaises(FileExistsError):m.publish(path,{'changed':True})
        self.assertEqual(path.read_bytes(),before);self.assertEqual(list(self.root.glob('.c1-inventory-*')),[])

    def test_cli_missing_input_is_sanitized_and_needs_no_ml_environment(self):
        missing=self.root/'secret-missing-path';output=self.root/'cli.gz'
        args=[sys.executable,'-E','-s','-S','-B',str(Path(m.__file__))]
        for key in ('original','confirmation','live','backup'):args += ['--'+key,str(missing)]
        args += ['--output',str(output)]
        p=subprocess.run(args,text=True,capture_output=True,check=True)
        r=json.loads(gzip.decompress(output.read_bytes()))
        self.assertEqual(r['state'],'inventory-partial-readiness-blocked')
        self.assertNotIn(str(missing),p.stdout+p.stderr+json.dumps(r))
        self.assertFalse(missing.exists())
        again=subprocess.run(args,text=True,capture_output=True)
        self.assertNotEqual(again.returncode,0)


if __name__=='__main__':unittest.main()
