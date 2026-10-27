"""Diagnostics explain a stop without changing the preflight decision or pin."""
from copy import deepcopy
import json
import unittest

from preflight_diagnostics import describe
from preflight_checks import fixture, edit, NOW
from preflight import _review


class DiagnosticsTests(unittest.TestCase):
    def test_matching_identity_is_not_an_approval(self):
        c,b=fixture(False); before=deepcopy((c,b))
        r=describe(c,baseline=b)
        self.assertEqual(r['deploymentComparison']['state'],'matches-pin')
        self.assertEqual(r['deploymentComparison']['changedFields'],[])
        self.assertFalse(r['executionApproved']);self.assertFalse(r['baselineChanged'])
        self.assertEqual((c,b),before)

    def test_four_read_deployment_stop_remains_blocked_and_is_explained(self):
        c,b=fixture(False);edit(c,-1,120,b'\x01')
        c['stoppedReason']='deployment-differs-from-pinned-observation'
        c['evidence']['blockTime']={'state':'not-requested'}
        c['evidence']['genesisAfter']={'state':'not-requested'}
        original=_review(c,b,NOW);r=describe(c,baseline=b)
        self.assertEqual(r['stoppedReason'],'deployment-differs-from-pinned-observation')
        self.assertEqual(r['deploymentComparison']['changedFields'],['payloadSha256'])
        self.assertTrue(r['deploymentComparison']['partialCaptureOnly'])
        self.assertEqual(original['reason'],'capture-incomplete')
        self.assertEqual(_review(c,b,NOW),original)

    def test_rpc_failure_and_http_status_are_distinct_from_deployment_drift(self):
        c,b=fixture(False)
        c['stoppedReason']='rpc-stopped-accounts'
        c['evidence']['accounts']={'state':'http-error','httpStatus':429,'error':'private provider text'}
        c['requests']=[{'method':'getMultipleAccounts','state':'http-error','elapsedMs':20,'url':'secret'}]
        r=describe(c,baseline=b)
        self.assertEqual(r['stoppedReason'],'rpc-stopped-accounts')
        self.assertEqual(r['httpStatuses'],{'accounts':429})
        self.assertEqual(r['deploymentComparison']['state'],'unavailable')
        self.assertNotIn('secret',json.dumps(r));self.assertNotIn('provider text',json.dumps(r))

    def test_untrusted_codes_keys_and_text_are_never_exported(self):
        c,b=fixture(False);c['stoppedReason']='secret'
        c['requests']=[dict(method='secret',state='secret',error='secret',httpStatus=True,elapsedMs=-1)]*100
        c['evidence']={'secret':'secret','accounts':{'state':'secret'}}
        r=describe(c,baseline=b)
        self.assertEqual(r['stoppedReason'],'unclassified');self.assertEqual(len(r['requests']),8)
        self.assertTrue(r['requestListTruncated']);self.assertNotIn('secret',json.dumps(r))

    def test_bad_or_oversized_accounts_cannot_create_an_identity(self):
        from program import MAX_BASE64
        for mode in ('missing','keys','slot','base64','huge'):
            c,b=fixture(False)
            if mode=='missing':c['evidence']['accounts']['result']['value'][-1]=None
            if mode=='keys':c['accountKeys'][-1]='wrong'
            if mode=='slot':c['evidence']['accounts']['result']['context']['slot']=0
            if mode=='base64':c['evidence']['accounts']['result']['value'][-1]['data'][0]='bad'
            if mode=='huge':c['evidence']['accounts']['result']['value'][-1]['data'][0]='x'*(MAX_BASE64+1)
            r=describe(c,baseline=b)
            self.assertEqual(r['deploymentComparison']['state'],'unavailable',mode)
            self.assertLess(len(json.dumps(r)),2000)

    def test_malformed_input_is_bounded(self):
        for c in (None,[],{},dict(stoppedReason={},evidence=[]),dict(requests=[None],evidence={})):
            r=describe(c);self.assertFalse(r['executionApproved'])
            self.assertLess(len(json.dumps(r)),2000)


if __name__=='__main__':unittest.main()
