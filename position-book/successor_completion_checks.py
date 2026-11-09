"""Real-clock disposable successor execution, receipt, accounting and balances.

All providers are synthetic. No operational path or closure authority is added.
"""
import base64
from copy import deepcopy
import io
import json
from pathlib import Path
from unittest.mock import patch

import admission_lifecycle as lifecycle
import admission_recovery as recovery
from admission_receipt_checks import receipt
from core import check
from journal import read_only_journals
import successor_accounting as accounting
import successor_balance as balance
import successor_execution_checks as execution

VERSION = 'successor-completion-rehearsal-1'
CONNECTED_CASES = 12


@balance.view.cycles.binding.operation
def recovery_projection(c):
    """Match recovery's operation owner, source lock and admission read lock."""
    f = c.f
    with balance.view.cycles.c.source_lock(f.home, f.wallet) as root, read_only_journals():
        with recovery.admission_read_lock(c.path):
            book = accounting.submission.transport._open(root, f.wallet, f.pool, c.clock)
            try: return recovery.retirement_projection(book, root, f.wallet, f.pool, c.clock)
            finally: book.close()


class ReceiptProvider(execution.Provider):
    def __init__(self, context):
        super().__init__(context.path)
        self.context = context
        self.package = self.scope = self.capture = None

    def open(self, request, timeout=None):
        with super().open(request, timeout) as response: result = json.load(response)
        if json.loads(request.data)['method'] == 'getTransaction':
            c = self.context; f = c.f
            book = accounting.submission.transport._open(f.home, f.wallet, f.pool, c.clock)
            try:
                expected = c.report['integration']['successorSha256']
                record, _, _, signed, _ = accounting.submission.load(f.home, book, f.wallet, f.pool, expected, c.clock)
                private, self.scope = accounting.receipts.original.private_intent(book, signed, record['candidate'])
                evidence = record['candidate']['evidence']
                self.capture = deepcopy(evidence['capture'])
                self.package = receipt(dict(scope=self.scope, costInputs=dict(
                    simulation_item=evidence['simulationItem'], price=evidence['price'])), private)
            finally: book.close()
            tx = self.package['bundle']['rpcEvidence']['transaction']['result']
            tx['slot'] = self.slot + 1
            result['result'] = dict(deepcopy(tx), transaction=[self.wire, 'base64'])
        return io.BytesIO(json.dumps(result).encode())


class BalanceProvider:
    """Build post-state independently from raw receipt arrays, not accounting."""
    def __init__(self, provider):
        roles = provider.scope['accounts']; self.clock = provider.context.clock
        self.keys = [roles[k] for k in ('wallet', 'destination', 'source', 'outputMint', 'inputMint')]
        tx = provider.package['bundle']['rpcEvidence']['transaction']['result']
        capture = provider.capture
        by_key = dict(zip(capture['accountKeys'], capture['evidence']['accounts']['result']['value']))
        self.rows = deepcopy([by_key[key] for key in self.keys])
        txkeys = tx['transaction']['message']['accountKeys']; self.slot = tx['slot']; self.calls = []
        self.rows[0]['lamports'] = tx['meta']['postBalances'][txkeys.index(self.keys[0])]
        for index in (1, 2):
            amount = next(row for row in tx['meta']['postTokenBalances']
                if row['accountIndex'] == txkeys.index(self.keys[index]))['uiTokenAmount']['amount']
            raw = bytearray(base64.b64decode(self.rows[index]['data'][0]))
            raw[64:72] = int(amount).to_bytes(8, 'little')
            self.rows[index]['data'] = [base64.b64encode(raw).decode(), 'base64']

    def open(self, request, timeout):
        q = json.loads(request.data); method = q['method']; self.calls.append(method)
        check(request.full_url == balance.original.ENDPOINT and 0 < timeout <= 10, 'completion-balance-provider')
        check(len(self.calls) <= 4 and method == balance.original.METHODS[len(self.calls)-1], 'completion-balance-order')
        if method == 'getGenesisHash':
            check(q['params'] == [], 'completion-balance-params'); value = balance.original.GENESIS['devnet']
        elif method == 'getMultipleAccounts':
            check(q['params'] == [self.keys, dict(encoding='base64', commitment='finalized', minContextSlot=self.slot)],
                'completion-balance-params')
            value = dict(context=dict(slot=self.slot), value=self.rows)
        else:
            check(q['params'] == [self.slot], 'completion-balance-params'); value = self.clock() // 1000
        return io.BytesIO(json.dumps(dict(jsonrpc='2.0', id=q['id'], result=value)).encode())


def connected(c):
    f = c.f; report = c.report; rpc = ReceiptProvider(c)
    with patch.object(execution, 'Provider', return_value=rpc): execution.connected(c)
    expected = report['integration']['successorSha256']
    with execution.fixture.phase(report, 'keyless-successor-accounting-after-stop'):
        check(not c.key.exists() and (f.home/'STOP').exists(), 'completion-keyless-stop')
        result = accounting._apply(f.home, f.wallet, f.pool, expected, allow_accounting=True, clock=c.clock)
        report['successorAccounting'] = result
        check(result['state'] == 'successor-accounted-flat-held' and result['appliedThisRun'], 'completion-accounting')
    report['cases']['raw-successor-receipt-accounted-keyless-after-stop'] = 'passed'
    with execution.fixture.phase(report, 'duplicate-accounting-lifecycle-and-recovery'):
        frozen = c.path.read_bytes()
        again = accounting._apply(f.home, f.wallet, f.pool, expected, allow_accounting=True, clock=c.clock)
        check(not again['appliedThisRun'] and again['recordSha256'] == result['recordSha256'], 'completion-duplicate')
        state = lifecycle.inspect(f.home, f.wallet, f.pool, clock=c.clock)
        check(state['coherent'] and state['phase'] == result['state'], 'completion-lifecycle')
        projected = recovery_projection(c)
        check(projected['successorAccountingSha256'] == result['recordSha256'] and
            projected['scopedAccounting'] == state['scopedAccounting'] and c.path.read_bytes() == frozen, 'completion-recovery')
        report['accountedHold'] = state['scopedAccounting']
    report['cases']['duplicate-accounting-and-independent-projections-agree'] = 'passed'
    with execution.fixture.phase(report, 'stop-blocks-balance-observation'):
        provider = BalanceProvider(rpc)
        stopped = balance.collect(f.home, f.wallet, f.pool, expected, opener=provider, clock=c.clock)
        check(stopped['diagnosticCode'] == 'balance-stopped' and not provider.calls and
            c.path.read_bytes() == frozen, 'completion-stop')
    report['cases']['stop-blocks-balance-requests-without-write'] = 'passed'
    # Only the STOP created by execution.connected in this disposable fixture.
    (f.home/'STOP').unlink()
    with execution.fixture.phase(report, 'real-clock-successor-balance-observation'):
        observed = balance.collect(f.home, f.wallet, f.pool, expected, opener=provider, clock=c.clock)
        report['successorBalances'] = observed
        report['balanceHeadroomAtReturnMs'] = (None if observed['snapshot'] is None else
            observed['snapshot']['validUntilExclusiveMs'] - c.clock())
        check(observed['state'] == 'successor-balances-match-held' and observed['headroomAtReturnMs'] > 0 and
            report['balanceHeadroomAtReturnMs'] > 0 and observed['networkRequests'] == len(provider.calls) == 4,
            'completion-balances')
        check(c.path.read_bytes() == frozen, 'completion-balance-write')
    report['cases']['four-raw-balance-reads-return-with-positive-headroom'] = 'passed'
    with execution.fixture.phase(report, 'completion-preserves-history-and-retired-exposure'):
        book = accounting.submission.transport._open(f.home, f.wallet, f.pool, c.clock)
        try: after = execution.fixture.table_rows(book)
        finally: book.close()
        check(all(after[k] == v for k, v in c.before_tables.items()), 'completion-old-history')
        check(set(after)-set(c.before_tables) == {'admission_exit_successor', 'admission_successor_signing',
            'admission_successor_transport', accounting.TABLE}, 'completion-tables')
        for name, raw in c.old_files.items(): check((c.path.parent/name).read_bytes() == raw, 'completion-old-marker')
        for name, raw in c.before_source.items():
            if Path(name) != c.key: check(Path(name).read_bytes() == raw, 'completion-old-source')
        held = report['accountedHold']; original = report['heldAccounting']
        check(int(held['retiredFeeExposureHeldLamports']) > 0 and
            int(held['feeHeldLamports']) >= int(held['retiredFeeExposureHeldLamports']) and
            int(held['feePaidLamports']) + int(held['feeHeldLamports']) ==
            int(original['feePaidLamports']) + int(original['feeHeldLamports']) and
            not held['scopedClosureRecorded'] and not observed['fundsAvailableForNewEntry'], 'completion-conservation')
        check(rpc.calls.count('sendTransaction') == 1 and not c.key.exists(), 'completion-no-resend')
    report['cases']['original-history-fee-conservation-and-retired-exposure-preserved'] = 'passed'
    report['completionPreservationPassed'] = True


def run():
    report = execution.fixture.run(_exercise=connected)
    report.update(format=VERSION, casesExpected=CONNECTED_CASES, executionApproved=False,
        scopedClosureRecorded=False, retiredExposureReleased=False,
        limitations=['Disposable keys, temporary journals and synthetic RPC only; no operational execution.',
            'Real-clock 1 MiB source. Send deadline and balance freshness are separate measured limits.',
            'Receipt and balances are synthetic; real provider latency and finality are not measured.',
            'Retired exposure remains held. No scoped closure, new entry or operational authorization.'])
    if report['casesPassed'] != CONNECTED_CASES or not report.get('completionPreservationPassed'):
        report['state'] = 'review-required'
    return report
