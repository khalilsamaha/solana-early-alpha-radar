"""Command boundary plus connected disposable-key acceptance routing, offline."""
from contextlib import ExitStack
from unittest.mock import patch
import controlled_acceptance as m
from core import check


def boundaries():
    cases = {}
    def refused(action, **kwargs):
        try: m.validate(action, **kwargs)
        except (ValueError, TypeError): return
        raise AssertionError('invalid command accepted')
    caps = dict(maximum_exit_attempts=2, maximum_exit_fee_lamports='10000', maximum_total_fee_lamports='30000')
    for action in m.SIGNING:
        for a,b in ((False,False),(True,False),(False,True),(1,True)):
            refused(action, allow_private_key_signing=a, allow_devnet_submit=b, **(caps if action=='entry' else {}))
    cases['signing-and-send-require-both-exact-opt-ins'] = 'passed'
    for action in m.RECONCILING:
        refused(action); refused(action, allow_reconcile=True, allow_devnet_submit=True)
        m.validate(action, allow_reconcile=True)
    cases['recovery-requires-reconcile-and-rejects-send-flags'] = 'passed'
    for flags in ({'allow_reconcile':True},{'allow_private_key_signing':True},{'allow_devnet_submit':True}): refused('status', **flags)
    m.validate('status'); cases['status-refuses-all-write-opt-ins'] = 'passed'
    for changes in ({'maximum_exit_attempts':0}, {'maximum_exit_attempts':4},
                    {'maximum_exit_fee_lamports':'10001'}, {'maximum_total_fee_lamports':'40001'},
                    {'maximum_total_fee_lamports':'20000'}, {'maximum_exit_attempts':True}):
        refused('entry', allow_private_key_signing=True, allow_devnet_submit=True, **dict(caps,**changes))
    refused('entry', allow_private_key_signing=True, allow_devnet_submit=True)
    m.validate('entry', allow_private_key_signing=True, allow_devnet_submit=True, **caps)
    cases['entry-requires-bounded-explicit-fee-policy'] = 'passed'
    for action in m.ACTIONS-{'entry'}:
        flags = dict(allow_private_key_signing=True,allow_devnet_submit=True) if action=='exit' else dict(allow_reconcile=True) if action in m.RECONCILING else {}
        refused(action, **flags, **caps)
    cases['later-actions-cannot-replace-entry-policy'] = 'passed'
    refused('retry'); cases['no-retry-or-new-cycle-action'] = 'passed'
    projected = m.projection(dict(state='submission-unknown', signedWireBase64='PRIVATE',
        diagnosticCode='PRIVATE exception with paths', nested={'secret':'PRIVATE'}, networkRequests=25))
    check(projected==dict(state='submission-unknown',networkRequests=25),'acceptance-projection')
    cases['public-output-allowlists-scalars-and-excludes-raw-evidence'] = 'passed'
    check(all(m.REQUEST_CEILINGS[k]==0 for k in ('status','recover-entry-signature','recover-exit-signature')) and
          all(m.REQUEST_CEILINGS[k]<=25 for k in m.ACTIONS),'acceptance-request-caps')
    cases['fixed-bounded-actions-have-no-endpoint-or-report-import'] = 'passed'
    return cases


def run():
    import lifecycle_rehearsal as rehearsal
    r = dict(format=m.VERSION+'-self-check', state='review-required', boundaryChecksPassed=0,
        connectedChecksPassed=0, cases={}, routedActions=[], lifecycle=None,
        realNetworkRequests=0, transactionsSent=0, productionWalletAccessed=False,
        runtimeIntegrated=False, executionApproved=False)
    r['cases'] = boundaries(); r['boundaryChecksPassed'] = len(r['cases'])
    def bridge(action, original):
        def wrapped(home, wallet, pool, **kwargs):
            actual = []
            def invoke(*args, **routed):
                # Keep synthetic transport/clock seams in this test wrapper only.
                # Operational dispatch has no opener, callback or imported-report argument.
                value = original(*args, **dict(kwargs, **routed)); actual.append(value); return value
            flags = dict(allow_private_key_signing=True,allow_devnet_submit=True) if action in m.SIGNING else dict(allow_reconcile=True)
            caps = {k:kwargs[k] for k in m.CAPS} if action=='entry' else {}
            with patch.dict(m.OPERATIONS, {action:invoke}):
                report = m.dispatch(action, home, wallet, pool, **flags, **caps)
            check(report['dispatchCompleted'] and len(actual)==1 and
                  report['state']==actual[0]['state'], 'acceptance-routing-failed')
            check(actual[0].get('networkRequests',0)<=report['maximumNetworkRequests'], 'acceptance-request-count')
            r['routedActions'].append(dict(action=action,state=report['state']))
            return actual[0]
        return wrapped
    with ExitStack() as stack:
        for module, name, action in ((m.fresh_entry,'prepare_sign_submit','entry'),
                (m.settled_exit,'advance','settle-entry'), (m.fresh_exit,'prepare_sign_submit','exit'),
                (m.exit_settlement,'advance','close-exit')):
            stack.enter_context(patch.object(module,name,bridge(action,getattr(module,name))))
        r['lifecycle'] = rehearsal.run()
    r['connectedChecksPassed'] = r['lifecycle']['casesPassed']
    expected = ['entry','settle-entry','exit','close-exit','close-exit']
    if (r['lifecycle']['state']=='offline-rehearsal-passed' and
            [x['action'] for x in r['routedActions']]==expected):
        r['state'] = 'offline-acceptance-passed'
    return r
