import asyncio
import copy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import contract as c
from capture import CaptureError, Limits, canonical, digest, exclusive_file
from shared_rehearsal import exercise


def metrics(count=24):
    row={'status':'local-measurement-replayed-live-blocked','selected_creations':count,
        'send_intents':count,'local_sends_completed':count,'send_intents_abandoned':0,
        'send_intents_without_completion_or_abandonment':0,'selected_without_completed_subscription_send':0,
        'gaps':0,'creation_records_observed':count,'unique_creation_mints_observed':count,
        'messages_counted':count,'raw_rows':count,'session_outcome':'capture-stopped',
        'creation_receive_to_local_send_return_ns':{'count':count,'min':100 if count else None,
                                                 'max':100 if count else None,'sum':100*count}}
    row.update({k:None for k in c.UNKNOWN});row.update({k:False for k in c.UNVERIFIED})
    return row


class ContractTests(unittest.TestCase):
    def evaluate(self,row,limits=None):
        return c.assess(row,asdict(Limits()) if limits is None else limits,c.proposal())

    def test_proposal_matches_current_capture_limits(self):
        p=c.proposal();self.assertEqual(p['limits'],asdict(Limits()))
        self.assertEqual(p['local_criteria']['minimum_selected_creations'],24)
        self.assertFalse(p['exposure']['owner_approved'])
        self.assertIsNone(p['exposure']['approved_exposed_balance_lamports'])

    def test_local_pass_never_clears_measurement_or_activation(self):
        r=self.evaluate(metrics())
        self.assertEqual(r['local_quality_verdict'],'pass')
        self.assertEqual(r['measurement_gate_verdict'],'insufficient')
        self.assertFalse(r['live_launch_authorized']);self.assertFalse(r['full_gate_accepted'])
        self.assertTrue(all(v is None for v in r['provider_evidence'].values()))

    def test_unsubscribe_completions_do_not_inflate_selected_subscription_fraction(self):
        row=metrics();row['send_intents']=48;row['local_sends_completed']=48
        r=self.evaluate(row)
        self.assertEqual(r['local_quality_verdict'],'pass')
        self.assertEqual(r['local_completion_fraction'],{'numerator':24,'denominator':24})
        self.assertEqual(r['local_receive_to_send_return_ns']['count'],24)
        self.assertFalse(r['full_gate_accepted'])

    def test_failed_unsubscribe_is_counted_without_fabricating_a_missing_subscription(self):
        row=metrics();row['send_intents']=25;row['send_intents_without_completion_or_abandonment']=1
        r=self.evaluate(row)
        self.assertIn('send_intents_without_completion_or_abandonment',r['local_failures'])
        self.assertEqual(r['local_completion_fraction'],{'numerator':24,'denominator':24})

    def test_small_and_empty_samples_are_insufficient_without_dividing_by_zero(self):
        for n in (0,1,23):
            r=self.evaluate(metrics(n));self.assertEqual(r['local_quality_verdict'],'insufficient')
            self.assertEqual(r['local_completion_fraction']['denominator'],n)

    def test_threshold_equality_and_exceedance(self):
        row=metrics();row['creation_receive_to_local_send_return_ns']={'count':24,'min':10**9,'max':10**9,'sum':24*10**9}
        self.assertEqual(self.evaluate(row)['local_quality_verdict'],'pass')
        row['creation_receive_to_local_send_return_ns']['max']+=1
        self.assertIn('local-send-return-latency',self.evaluate(row)['local_failures'])

    def test_gap_is_failure_even_with_insufficient_sample(self):
        row=metrics(1);row['gaps']=1
        self.assertEqual(self.evaluate(row)['measurement_gate_verdict'],'fail')

    def test_failure_and_cancellation_do_not_become_clean_stops(self):
        for outcome in ('transport-failed','transport-cleanup-failed','transport-cancelled'):
            row=metrics();row['session_outcome']=outcome
            self.assertIn('session-not-cleanly-stopped',self.evaluate(row)['local_failures'])

    def test_abandoned_and_unresolved_sends_fail(self):
        for key in ('send_intents_abandoned','send_intents_without_completion_or_abandonment'):
            row=metrics();row[key]=1;row['local_sends_completed']-=1
            row['selected_without_completed_subscription_send']=1
            row['creation_receive_to_local_send_return_ns'].update(count=23,sum=2300)
            self.assertIn(key,self.evaluate(row)['local_failures'])

    def test_different_sampling_limits_are_insufficient(self):
        limits=asdict(Limits(sample_modulus=1))
        self.assertIn('capture-limits-differ-from-contract',self.evaluate(metrics(),limits)['local_insufficient'])

    def test_false_unknown_billing_or_provider_claims_are_rejected(self):
        for key in c.UNKNOWN:
            for value in (0,False,24):
                row=metrics();row[key]=value
                with self.assertRaises(CaptureError):self.evaluate(row)
        for key in c.UNVERIFIED:
            row=metrics();row[key]=True
            with self.assertRaises(CaptureError):self.evaluate(row)

    def test_missing_unknown_is_not_treated_as_available(self):
        row=metrics();del row['data_fees_lamports']
        with self.assertRaises(CaptureError):self.evaluate(row)

    def test_bool_negative_and_inconsistent_denominators_are_rejected(self):
        for key,value in (('selected_creations',True),('gaps',-1),('local_sends_completed',25),
                          ('creation_records_observed',23),('messages_counted',23)):
            row=metrics();row[key]=value
            with self.assertRaises(CaptureError):self.evaluate(row)

    def test_latency_count_and_bounds_are_consistent(self):
        for key,value in (('count',23),('min',-1),('max',False),('sum',2399),('sum',2401)):
            row=metrics();row['creation_receive_to_local_send_return_ns'][key]=value
            with self.assertRaises(CaptureError):self.evaluate(row)

    def test_proposal_cannot_grant_approval_or_silently_retune(self):
        for path,value in ((('live_launch_authorized',),True),(('schema_version',),True),
            (('local_criteria','minimum_selected_creations'),1), (('exposure','owner_approved'),True),
            (('exposure','funding_ceiling_lamports'),50000000), (('extra',),'hidden')):
            p=copy.deepcopy(c.proposal());target=p
            for key in path[:-1]:target=target[key]
            target[path[-1]]=value
            with self.assertRaises(CaptureError):c.validate_proposal(p)

    def test_freeze_load_and_exclusive_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);receipt=c.freeze(root)
            self.assertEqual(c.load(root/'contract.json',receipt['contract_sha256'])['proposal'],c.proposal())
            before=(root/'contract.json').read_bytes()
            with self.assertRaises(FileExistsError):c.freeze(root)
            self.assertEqual((root/'contract.json').read_bytes(),before)

    def test_tamper_hash_format_duplicate_keys_and_extra_fields_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);r=c.freeze(root);path=root/'contract.json';original=path.read_bytes()
            for raw in (original+b' ',original.replace(b'"schema_version":1',b'"schema_version":1,"schema_version":1',1),
                        original.replace(b'"schema_version":1',b'"extra":1,"schema_version":1',1)):
                path.write_bytes(raw)
                with self.assertRaises(CaptureError):c.load(path,r['contract_sha256'])
                with self.assertRaises(CaptureError):c.load(path,digest(raw))
            for value in ('',True,'g'*64):
                with self.assertRaises(CaptureError):c.load(path,value)

    def test_source_change_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);r=c.freeze(root);changed=c.pins();changed['r1-registration/contract.py']='0'*64
            with patch.object(c,'pins',return_value=changed):
                with self.assertRaises(CaptureError):c.load(root/'contract.json',r['contract_sha256'])

    def test_symlink_input_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);r=c.freeze(root);link=root/'alias';link.symlink_to(root/'contract.json')
            with self.assertRaises(CaptureError):c.load(link,r['contract_sha256'])

    def test_real_session_replay_and_wrong_bundle_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);r=c.freeze(root)
            case=asyncio.run(exercise(root/'fixture',transport='pipe'))
            bundle=root/'fixture/export/session.zip'
            result=c.review(root/'contract.json',r['contract_sha256'],bundle,case['session_bundle_sha256'],root/'replay')
            self.assertTrue(result['complete_session_independently_replayed'])
            self.assertEqual(result['measurement'],case['measurement'])
            self.assertEqual(result['local_quality_verdict'],'insufficient')
            self.assertFalse(result['precollection_registration_proven'])
            with self.assertRaises(CaptureError):c.review(root/'contract.json',r['contract_sha256'],bundle,'0'*64,root/'bad')


if __name__=='__main__':unittest.main()
