import copy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import experiment as ex
import failure_audit as f
from audit import digest, publish
from model import freeze, evaluate, seal
from test_model import training


class FailureAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.train, reg, now = training()
        cls.model = freeze(cls.train, reg, now)
        cls.start = now+600000

    def fixture(self):
        model = copy.deepcopy(self.model)
        data = copy.deepcopy(self.train)
        for i in range(4):
            row = copy.deepcopy(data['rows'][0])
            row.update(id='forward'+str(i), seq=1000+i, mint='new'+str(i),
                       signalAt=self.start+i*1000, utcDay='2026-10-22')
            row['targets']['30000']['availableAt'] = row['signalAt']+31000
            if i == 1:
                row['exitAvailability']['30000'] = 'provider-reported-quote-failure'
                row['targets']['30000'].update(returnPct=None, state='sell-quote-failed', onTime=None)
            if i == 2:
                row['exitAvailability']['30000'] = 'transport-or-service-failure'
                row['targets']['30000'].update(returnPct=None, availableAt=None, state='sell-quote-failed', onTime=None)
            if i == 3:
                row['supplementalEntryContext']['predictors']['liquidityUsd'] = None
            data['rows'].append(row)
        data['capturedAt'] = self.start+100000
        reg = dict(testNotBeforeAt=self.start, artifactSha256=digest(model))
        evidence = dict(inputs=[], captureCount=0)
        report = evaluate({**data, 'rows': data['rows'][-4:]}, model)
        report.update(experiment=reg, evidenceMerge=evidence,
                      beforeExperimentStartExcluded={'baseline':120}, networkRequests=0)
        return data, model, reg, evidence, report

    def test_replay_retains_failures_unknowns_and_frozen_state_without_fit(self):
        args = self.fixture(); before = copy.deepcopy(args)
        with patch('model.fit', side_effect=AssertionError('must not fit')):
            r = f.analyze(*args)
        self.assertEqual(args, before)
        g = r['groups'][0]
        self.assertEqual(g['watches'],4)
        self.assertEqual(set(g['byPrimaryExitState']), {'on-time-validated-quote',
                         'provider-reported-quote-failure','transport-or-service-failure'})
        self.assertEqual(g['byPrimaryExitState']['transport-or-service-failure']['responseAfterSignalMs']['missing'],1)
        for parts in g['fixedThresholdPartitions'].values():
            self.assertEqual(sum(v['watches'] for v in parts.values()),4)
            self.assertEqual(sum(v['unknownReturnLabels'] for v in parts.values()),2)
        self.assertFalse(r['liveUseAllowed']);self.assertFalse(r['modelRefitted'])
        self.assertEqual(r['decision'],'not-promoted')

    def test_exact_training_ids_required_before_claiming_distribution(self):
        args = self.fixture();r=f.analyze(*args)
        self.assertEqual(r['groups'][0]['trainingReconstruction']['state'],'matched-frozen-training-ids')
        args[0]['rows'].pop(0)
        args[4]['beforeExperimentStartExcluded']['baseline']-=1
        r=f.analyze(*args)
        self.assertEqual(r['groups'][0]['trainingReconstruction']['state'],'training-capture-not-exact')
        self.assertIsNone(r['groups'][0]['trainingReconstruction']['features'])

    def test_tampered_summary_prediction_identity_and_cutoff_rejected(self):
        changes=[lambda r:r.update(artifactSha256='bad'),
                 lambda r:r.update(capturedAt=r['capturedAt']+1),
                 lambda r:r['groups'][0]['predictions'][0]['probabilities'].update(context=.123),
                 lambda r:r['groups'][0]['predictions'][0].update(id='wrong'),
                 lambda r:r['groups'][0]['allForwardOutcomes']['30000'].update(meanQuotedPct=99),
                 lambda r:r.update(modelRefitted=True)]
        for change in changes:
            args=self.fixture();change(args[4])
            with self.assertRaises(ValueError):f.analyze(*args)

    def test_comparator_allows_only_tiny_finite_float_rounding(self):
        self.assertTrue(f.equivalent({'v':.25},{'v':.25+1e-14}))
        for a,b in [(1,True),(1,1.0),(.25,.25001),(float('nan'),float('nan')),({'a':1},{'a':1,'b':2})]:
            self.assertFalse(f.equivalent(a,b))

    def test_zero_and_missing_remain_distinct(self):
        r=f.summary([0,None,2]);self.assertEqual((r['known'],r['missing'],r['zero']),(2,1,1))
        self.assertIsNone(f.summary([None])['median'])
        with self.assertRaises(ValueError):f.summary([float('inf')])

    def test_shift_is_input_only_and_uses_frozen_missing_indicators(self):
        args=self.fixture();rows=args[0]['rows'][-4:];w=args[1]['groups'][0]['models']['context']
        result=f.inputs_against_frozen_transform(rows,'baseline','context',w)
        self.assertEqual(result['liquidityUsd']['missing'],1)
        self.assertEqual(result['liquidityUsd']['forwardMissingFraction'],.25)
        for row in rows:row['targets']['30000']['returnPct']=-999
        self.assertEqual(f.inputs_against_frozen_transform(rows,'baseline','context',w),result)

    def test_index_hash_is_raw_decoded_content_not_reencoded_json(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);raw=b'{ "complete": true }\n'
            (p/'capture-index.json.gz').write_bytes(gzip.compress(raw))
            self.assertEqual(f.index_hash(p),hashlib.sha256(raw).hexdigest())
            (p/'capture-index.json.gz').write_bytes(gzip.compress(b'x'*65537))
            with self.assertRaises(ValueError):f.index_hash(p)

    def test_run_preserves_files_selects_reviewed_indexes_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);directory=root/'private';source=root/'model.gz'
            publish(source,seal(self.model))
            with patch.object(ex,'ARTIFACT_SHA256',digest(self.model)), \
                 patch.object(ex,'clock',return_value=self.start+200000), \
                 patch.object(f,'clock',return_value=self.start+200000):
                ex.install(source,directory,self.start-300000)
                model,reg=ex.load(directory)
                args=self.fixture();data=args[0];capture=root/'capture';capture.mkdir()
                (capture/'capture-index.json.gz').write_bytes(gzip.compress(b'{"test":1}'))
                extra=root/'later';extra.mkdir();(extra/'capture-index.json.gz').write_bytes(gzip.compress(b'{"test":2}'))
                evidence={'inputs':[{'indexSha256':f.index_hash(capture)}],'captureCount':1}
                report=evaluate({**data,'rows':data['rows'][-4:]},model)
                report.update(experiment=reg,evidenceMerge=evidence,beforeExperimentStartExcluded={'baseline':120},networkRequests=0)
                reviewed=root/'review.gz';publish(reviewed,report);output=root/'audit.gz'
                before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
                with patch.object(f,'combine',return_value=(data,evidence)) as combined:
                    f.run(directory,[extra,capture],reviewed,output)
                    combined.assert_called_once_with([capture])
                self.assertEqual(output.stat().st_mode&0o777,0o600)
                for p,content in before.items():self.assertEqual(Path(p).read_bytes(),content)
                with self.assertRaises(ValueError):f.run(directory,[capture],reviewed,output)
                with self.assertRaises(ValueError):f.run(directory,[capture],reviewed,directory/'audit.gz')

    def test_missing_or_duplicate_capture_fails_before_publication(self):
        args=self.fixture()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);reviewed=root/'review.gz';output=root/'audit.gz'
            report=args[4];report['evidenceMerge']={'inputs':[{'indexSha256':'missing'}]}
            publish(reviewed,report)
            with patch.object(f,'load',return_value=(args[1],args[2])):
                with self.assertRaises(ValueError):f.run(root,[],reviewed,output)
            self.assertFalse(output.exists())

    def test_real_capture_chunks_and_registration_replay_without_source_writes(self):
        from test_audit import sample
        from test_history import ledger
        import history
        q=sample()
        at=q['signals'][0]['signalAt']
        model=copy.deepcopy(self.model)
        model.update(frozenAt=at-600000,trainingCutoffAt=at-900000,
                     testNotBeforeAt=at-300000,seenTrainingMints=[])
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);db=root/'ledger';capture=root/'capture';source=root/'model.gz';directory=root/'private'
            ledger(db,[q]);history.capture(db,capture,hours=3,chunk_hours=1,evidence_cutoff=at+3600000)
            publish(source,seal(model))
            with patch.object(ex,'ARTIFACT_SHA256',digest(model)), \
                 patch.object(ex,'clock',return_value=at+7200000), \
                 patch.object(f,'clock',return_value=at+7200000):
                ex.install(source,directory,model['frozenAt'])
                reviewed=root/'review.gz';publish(reviewed,ex.review(directory,[capture]))
                before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
                with patch('model.fit',side_effect=AssertionError('no fit')):
                    result=f.run(directory,[capture],reviewed,root/'diagnostic.gz')
                self.assertEqual(result['state'],'review-replayed-diagnostics-only')
                self.assertEqual(result['groups'][0]['watches'],1)
                for p,content in before.items():self.assertEqual(Path(p).read_bytes(),content)
                with self.assertRaises(ValueError):f.run(directory,[capture,capture],reviewed,root/'duplicate.gz')
                self.assertFalse((root/'duplicate.gz').exists())
                part=capture/'part-00.json.gz';part.write_bytes(part.read_bytes()+b'tamper')
                with self.assertRaises(ValueError):f.run(directory,[capture],reviewed,root/'tampered.gz')
                self.assertFalse((root/'tampered.gz').exists())


if __name__=='__main__':unittest.main()
