# Connected lifecycle timing and recovery rehearsal — November 3, 2026

The exit settlement host report captured on November 3 at 04:07:01 UTC passed
all 21 checks and exactly matched the released portable contract. This increment
measures the connected two-transaction path on the host without targeting any
existing wallet, scanner data, private rehearsal directory or provider.

## What runs

`position-book/lifecycle_rehearsal_cli.py` accepts only an output filename. It
creates disposable historical journals and test keys inside an owned temporary
directory, then runs the actual collectors, isolated Node signers, one-send
boundaries, receipt accounting and scoped closure against synthetic HTTP replies.
Real Python socket access is blocked throughout. No runtime component is modified.

| Measured stage | Evidence |
| --- | --- |
| Fixture setup | Disposable historical source and test-key generation; excluded from transaction-leg timings |
| Entry collection, signing and send | Fresh evidence, original expiry checks, one synthetic send with deliberately lost response |
| Entry receipt and accounting | Recovery of the original signature, acquired delta and remaining fee commitments; no signing |
| Exit collection, signing and send | Separately collected exit, independent test-key signing, one synthetic send with lost response |
| Exit receipt, accounting and closure | Exact effects, fresh account balances and scoped closure; caller loses the response after commit |
| Read-only recovery | Key removed, STOP set; durable closure and conservation replayed without RPC |
| Repeated recovery | Same closure identity and journal bytes; no second release, receipt read, signer or sender |

The nine connected assertions also check historical source preservation (apart
from the deliberately added test STOP), protected inventory, fee conservation and
absence of authority to reuse released proceeds for a new entry.

## Reading the report

A successful report says `offline-rehearsal-passed`, contains nine passed checks
and seven nonnegative monotonic stage timings. Each timing is inclusive. This is
one host sample, not a latency distribution or a performance guarantee.

Synthetic provider replies incur no real RPC delay; synthetic receipts incur no
chain confirmation wait. Both entry and exit retain their original deadlines and
normal shared operation budgets. The rehearsal does not relax these controls to
obtain a passing result. A slower host can produce `review-required`; that failure
is useful evidence, not a reason to increase the expiry automatically.

A lost send response is not reported as a failed trade. The original signature is
reconciled. A lost closure response is initially unknown, then independently
replayed. The final historical close still does not establish current wallet-wide
solvency, allocate funds to another entry, approve mainnet or establish profitability.

Failures produce a sanitized public report with the last stage and measured
partial progress. The CLI exits with status 2 for a completed failure report.
Unknown exceptions are not exported. The enclosing temporary directory also owns
partially constructed fixtures, so failed setup does not strand test keys. Existing
output files are never overwritten and reports are written with mode 0600.

## Validation

The connected CLI test runs the complete path using disposable keys, checks all
nine assertions and report privacy, then verifies output exclusivity and rejection
of operational flags. Unit checks cover invalid stages, exception timing,
monotonic clock regression/nonfinite values, failed/late send projections,
partial setup cleanup and cleanup failure reporting. Source hygiene and stable CI
partition checks accompany the release. All nine local tests passed, including
the complete connected CLI test, along with both partition checks and tracked
source hygiene. Kali acceptance passed at 04:17:47 UTC on November 3: all nine
connected checks and seven timed stages completed. See the
[consolidation record](LIFECYCLE-CONSOLIDATION-20261103.md) for timings and limits.

## Kali acceptance and remaining work

Run the pinned command supplied in chat and upload its `.json.gz` report. No
Docker rebuild or restart, private wallet argument or devnet funding is required.
Node and Python already installed on Kali are used. Temporary fixture setup may
take tens of seconds; it is reported separately from the measured legs.

After host acceptance, consolidate the three accepted increments (fresh exit,
settlement, connected rehearsal) and run the grouped CI before merging. Then
scope the controlled devnet acceptance command: explicit wallet/pool and fee
limits, one-send execution, original deadlines, raw receipt reconciliation and
read-only recovery. Real provider latency and confirmation behavior must be
measured there; this offline profile cannot substitute for that evidence.

The availability-study captures on November 3, 5 and 6 and review on November 6
at 00:05 UTC / 01:05 Amsterdam remain unchanged. Scanner rules, Telegram,
provider limits, frozen models, backups and production execution are unchanged.
