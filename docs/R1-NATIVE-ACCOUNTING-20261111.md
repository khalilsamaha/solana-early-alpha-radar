# R1 native-SOL accounting — development validated, Kali pending

Date: 2026-11-11. Continuation of the existing R1 source-feasibility gate, within
the unchanged five-working-day build/validation limit. The preceding 137-test
schema comparison is Kali accepted; its acceptance and input hashes are recorded
in [R1-TRADE-SCHEMA-COMPARISON-20261111.md](R1-TRADE-SCHEMA-COMPARISON-20261111.md).

## Findings from the saved evidence

All three saved transactions' account-level lamport changes reconcile exactly
to parsed System transfers/createAccount funding plus the transaction fee.
There are zero residual lamports on every account. Both saved native-SOL buys
also match 16 narrow identity/arithmetic checks against their reported events.
This is consistency of retained provider evidence, not cryptographic execution
proof, historical configuration verification or executable price simulation.

All quantities below are integer lamports. Case 2 contains creation only.

| Quantity | Case 1 | Case 2 | Case 3 |
| --- | ---: | ---: | ---: |
| Buy payment to curve | 987654320 | — | 197530863 |
| Reported protocol fee, including buyback portion | 9382717 | — | 1876544 |
| Transfer to protocol fee recipient | 9382717 | — | 938272 |
| Transfer to buyback recipient | 0 | — | 938272 |
| Reported creator fee, uniquely matched to one transfer | 2962963 | — | 592593 |
| Curve payment plus reported fees | 1000000000 | — | 200000000 |
| Additional creator-vault transfer, purpose unverified | 0 | — | 650240 |
| Account creation funding inside buy parent | 0 | — | 1346200 |
| All System outflows inside buy parent | 1000000000 | — | 201996440 |
| All transaction System outflows from user | 1009961880 | 5623560 | 209301480 |
| Transaction fee paid by user | 40534 | 10000 | 32948 |
| Full observed/explained wallet debit | 1010002414 | 5633560 | 209334428 |
| Absolute account-balance residual | 0 | 0 | 0 |

Case 3 demonstrates two important distinctions. The 938272-lamport buyback
transfer is part of the reported protocol fee, not an additional 938272 to add
again. The 650240-lamport creator-vault transfer is separate from the reported
592593-lamport creator fee. It is retained with unknown purpose. Documentation
allows creator-vault top-ups, but the necessary historical rent/account evidence
has not been read to establish that interpretation or refundability here.

The instruction's max cost is 1010000000 for case 1 and 202000000 for case 3.
The trade plus reported fees fits those caps. Creation funding, account funding
and the network fee remain separately measured; neither the cap nor the event's
SOL amount is treated as the whole transaction's wallet debit. Combined
create-and-buy costs cannot be assumed to be repeat-trade costs.

Both events report protocol fee rate 95 basis points and creator fee rate 30.
Their amounts equal ceiling(SOL-to-curve * reported bps / 10000). Case 3 reports
buyback rate 5000 and amount floor(protocol fee * 5000 / 10000); case 1 reports
zero. These are exact arithmetic comparisons on this sample, not universal
rounding rules, independently verified historical fee tiers or future rates.

Creation-event virtual token and real token reserves each decrease by the
purchased token amount; virtual SOL reserves increase by the curve payment.
Reported real SOL reserves equal that first payment, consistent with the
documented zero initial real SOL model. Native quote/SOL reserve aliases agree.
These comparisons do not read historical curve account data. The Mayhem
creation supply/MintTo difference remains intact; no universal supply model or
constant-product execution model is inferred from these equalities.

## Sources and boundaries

Primary documentation snapshot, commit
`639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22`:

- [Buy V2 accounts and arguments](https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/docs/instructions/BUY.md): native-SOL account roles, exact amount and max-cost arguments, account-funding possibilities.
- [Pump program reserve model](https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/docs/PUMP_PROGRAM_README.md): reported initial reserves and directional buy changes.
- [Fee program](https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/docs/FEE_PROGRAM_README.md): rates can depend on configuration and market-cap tier; a sample event is not a historical configuration read.
- [Fee retention distinctions](https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/docs/VIRTUAL_QUOTE_RESERVES_FEE_ADJUSTMENT.md): distinguish Pump buy_v2 from PumpSwap and newer fee-retaining paths.

The accepted 36-field TradeEvent extraction remains a separate diagnostic
profile. Its source archive checksum, deployed binary and activation range are
still unverified. No SDK is installed or executed, and no new RPC request or
historical account snapshot was obtained. The supported scope is one creation
and at most one direct native-SOL buy_v2 per transaction. Multiple buys, other
versions, cashback, holder rewards, shareholder splits, retained creator fees
and quote transfer fees remain unsupported in this accounting increment.

## Implementation and adversarial checks

`accounting_inspect.py` replays both accepted inspectors before accounting. Their
implementations and schemas are unchanged. The new checker validates exact buy
argument length, final event position, distinct payment roles, fee/creator/mode
identity, transfer sums, unique creator-fee assignment, reported fee arithmetic,
cost cap and reported reserve changes. Extra transfers remain visible; unknown
purposes are not resolved by matching their amount to a preferred explanation.

The System-move pass indexes every top-level and inner instruction once,
recognizes transfer/createAccount only, and debits the reported network fee from
the first signer account. Expected and reported net balances are compared for
every transaction account, not only the buyer or a global sum. An unexplained
change on any account remains a mismatch. Duplicate keys/groups, unknown System
instructions, missing balances, bool/float/negative/overflow amounts and ambiguous
fee roles cannot pass. Other programs may change lamports directly: net agreement
does not establish that every internal operation was captured, especially if
unobserved changes cancel. The tool makes no instruction-completeness claim.

The CLI uses bounded reads/decompression, original RPC replay/source pins,
source hashes before/after, and private atomic output with replacement refused.
It exports quantities and checks, not raw identities or token metadata. Exit
zero means a diagnostic report was written; per-case mismatches/unsupported
states do not become successes. Historical fee config, curve account validation,
deployed version, fee model, reconstruction, profitability and live activation
remain explicitly false even when every diagnostic check agrees.

Development suite: **152 tests**, zero errors/failures/skips, including 15 new
accounting tests and the existing capture/restore rehearsal. Tests include split
fees and extra funding, mismatched reserves/recipients/rates, ambiguous creator
payments, instruction caps, unsupported fee modes, event ordering, account-role
aliasing, stack height, per-account offsetting discrepancies, missing balances,
separate fee payer/incoming payments, creation-only transactions, integer bounds,
input corruption/size limits, source pins, sanitized errors and preservation.
The runner pins 19 files; the accounting report pins eight.

The final standalone run used Python 3.12.14 and SQLite 3.53.1, with
ResourceWarning treated as an error, and took 1.037227 seconds. Internet socket
creation was forbidden for the full suite. All socket creation was forbidden
for the synchronous real-evidence inspectors. An earlier overly broad harness
also blocked asyncio's local Unix socket pairs and stopped the suite without a
pass report; narrowing that external guard to internet sockets resolved the
harness failure without changing application code or relaxing warning handling.

Final development runner report SHA-256:
`d7d0631f13f49ee54de858d2ff74475759cf8f021fb799be566cd49dff54ddde`.
Saved-bundle accounting report SHA-256:
`f495fe0798940504502b14f120cf901fde4306ba9d82bd42ab6f9f9fd7704217`.
Original input bytes were preserved. The unchanged schema comparator reproduced
the accepted Kali report byte for byte. These reports and the private bundle
are not committed to Git. This development validation is not Kali acceptance.

## Required Kali acceptance and next boundary

Run the pinned development commit's `r1-data/check.py`, then
`r1-data/accounting_inspect.py` with the original saved RPC report and gzip bundle.
Upload the two new JSON reports. Expected runner status:
`offline-accounting-inspector-passed-live-blocked`, 152 tests and no
failures/errors/skips. Expected diagnostic status:
`offline-accounting-inspection-complete-live-blocked`; cases 1 and 3
`observed-accounting-consistent-live-blocked`, case 2
`creation-only-accounting-consistent`, zero net-balance residuals for all three.

After Kali acceptance, the remaining source-feasibility decision must address
historical version/configuration applicability and an executable pricing model,
alongside connection coexistence, early-event capture/gap recovery, adapter and
preservation requirements. Do not turn further arithmetic matches into economic
or paid-feed acceptance. Keep the five-working-day R1 limit; if required evidence
is unavailable at that endpoint, record an explicit limited/incomplete verdict
instead of extending the gate through more diagnostic substeps. ML fitting and
profitability evaluation do not start from this three-transaction sample.

Development-branch upload only. Full-gate Kali validation and the agreed owner
decision precede PR/CI consolidation or merge. No funding, real transaction,
scanner restart, deployment or production modification belongs to this increment.
