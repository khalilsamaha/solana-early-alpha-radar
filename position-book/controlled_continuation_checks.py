"""Portable command-boundary checks; connected signer rehearsal is separate."""
import json
import tempfile
from unittest.mock import Mock, patch
import controlled_continuation as m


def run():
    flags = dict(expected_original_sha256='a'*64, expected_current_sha256='b'*64, allow_unsigned_continuation=True,
        allow_private_key_signing=True, allow_devnet_submit=True)
    cases = {}
    with patch.object(m, 'directory', side_effect=AssertionError('source accessed')):
        for key in ('allow_unsigned_continuation', 'allow_private_key_signing', 'allow_devnet_submit'):
            for value in (False, 1, 'yes', None):
                try: m.execute('/missing', 'w', 'p', **dict(flags, **{key:value}))
                except ValueError: pass
                else: raise AssertionError('invalid opt-in')
            cases[key+'-exact-before-source'] = 'passed'
        for value in (None, '', 'A'*64, 'a'*63, 'g'*64, 'a'*64+'\n'):
            try: m.execute('/missing', 'w', 'p', **dict(flags, expected_original_sha256=value))
            except ValueError: pass
            else: raise AssertionError('invalid identity')
        cases['exact-original-identity-before-source'] = 'passed'
        for value in (None,'','a'*64,'B'*64,'b'*63,'g'*64,'b'*64+'\n'):
            try:m.execute('/missing','w','p',**dict(flags,expected_current_sha256=value))
            except ValueError:pass
            else:raise AssertionError('invalid current identity')
        cases['distinct-exact-current-identity-before-source']='passed'
    with tempfile.TemporaryDirectory() as d:
        target = Mock(return_value=dict(state='exit-submission-unknown', sendRequestsThisRun=1,
            signedWireBase64='PRIVATE', preparation={'recordSha256':'c'*64,
            'originalPreparationSha256':'a'*64,'previousPreparationSha256':'b'*64,'createdThisRun':True,'continuationCount':1,
            'originalPreserved':True,'evidence':'PRIVATE'}))
        with patch.object(m, 'EXECUTE', target): r = m.execute(d, 'w', 'p', **flags)
        assert target.call_count == 1 and target.call_args.kwargs == flags
        assert 'PRIVATE' not in json.dumps(r) and r['preparation']['recordSha256']=='c'*64 and r['preparation']['previousPreparationSha256']=='b'*64
        assert m.exit_code(r)==2 and not r['automaticRetryAllowed']
        cases['one-fixed-dispatch-with-safe-evidence'] = 'passed'
        target = Mock(side_effect=OSError('PRIVATE committed response lost'))
        with patch.object(m, 'EXECUTE', target): r = m.execute(d, 'w', 'p', **flags)
        assert target.call_count == 1 and r['result'] is None and r['preparation'] is None
        assert not r['dispatchCompleted'] and 'PRIVATE' not in json.dumps(r)
        cases['exception-preserves-unknown-effects-without-retry'] = 'passed'
    for state in ('exit-submission-unknown','inspection-required','quarantined','future-state'):
        assert m.exit_code(dict(state=state,dispatchCompleted=True,result={}))==2
    assert m.exit_code(dict(state='rpc-acknowledged',dispatchCompleted=True,
                           result={'completedWithinOriginalDeadline':False}))==2
    assert m.exit_code(dict(state='rpc-acknowledged',dispatchCompleted=True,
                           result={'completedWithinOriginalDeadline':True}))==0
    cases['unknown-late-or-failed-is-nonzero'] = 'passed'
    return dict(format=m.VERSION+'-self-check',state='offline-boundaries-passed',
        cases=cases,casesPassed=len(cases),realNetworkRequests=0,productionWalletAccessed=False,
        transactionsSent=0,productionLedgerUpdated=False,executionApproved=False,
        runtimeIntegrated=False,automaticRetryAllowed=False,
        limitations=['Command boundary tests; the separate connected rehearsal validates signing and transport.',
                     'No live-state or latency acceptance; no transaction sent.'])
