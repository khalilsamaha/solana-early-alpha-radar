# Fresh delayed exit preparation

The October 31 recovery report passed all 19 actual tests. Its case-list formatter
also labelled a non-callable `test_key` attribute as a case: the count was 19 but
the map had 20 names. No key value was exported. This release uses unittest's
callable test discovery and adds a regression check for that discrepancy.

## What this increment adds

`position-book/admission_exit.py` prepares one immutable, unsigned first exit in
the same admission database that holds entry accounting. The internal caller must
supply new raw pool, account, deployment, message-fee and simulation evidence.
No public report or declared reservation can substitute for those inputs.

Preparation requires a collected, replayable successful entry receipt and a saved
entry-accounting record. It rejects a failed, unknown or quarantined entry. It
reverses the original accounts, mints and vaults and uses exactly the acquired
delta. Existing and surplus token holdings are protected from this exit.

The entry may already be expired: the exit has its own observation window,
blockhash, message, fee evidence and deadline. All new observations start after
entry accounting, and quote/account/simulation slots cannot predate the receipt.
The original entry blockhash cannot be reused. The pinned deployment, raw pool
arithmetic, exact unsigned message, simulation's own balance effects and fee are
recomputed. Missing metadata, drift, stale evidence and inconsistent effects stop
preparation without a record.

The exit's cap must fit one held attempt. Current native funds must also cover
the rest of the remaining fee commitment. This neither consumes an attempt nor
releases unused entry fees or future exit fees. No second position book is created.
The original entry admission and accounting remain unchanged.

## Durable behavior and recovery

The cooperating source lock and a SQLite writer transaction cover validation and
the single-record commit. An independent read-only connection replays the entry
and original historical source. The freshness deadline is checked after expensive
validation and again after the write, before commit. A failed check rolls back.

The record stores bounded private raw evidence and its derived binding. Repeating
the same preparation is idempotent, including after expiry; it never renews the
deadline. Different replacement evidence is refused. Read-only status replays the
historical record and labels expiry or STOP. There is no delete, replacement,
refresh, retry, release or execution interface.

Combined admission snapshots now replay this optional exit record when present.
Snapshots created before exit preparation remain verifiable. A corrupted record
cannot pass merely because its outer checksums were recomputed. The isolated copy
remains stopped and is never restored over active state.

## Host check

Local validation passed 17 exit/report tests plus 20 recovery/integration tests
(including the 19 existing recovery regressions). The callable-only report test
also passed against the real CLI with a disposable test module. Source hygiene
and diff checks passed. Kali acceptance of the 27-case portable report is pending.

After checking out the exact commit supplied in chat:

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/position-book/admission_exit_cli.py" \
  --output "$PWD/radar-admission-exit-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, **27 cases**. These use temporary ledgers,
synthetic account/RPC evidence and the existing public signature fixture. They
make no network calls, access no private keys and send no transactions. Upload
only the public report. No sudo, Docker rebuild or service restart is required.

Local integration tests additionally cover concurrent writers, rollback,
rehashed tampering, source-binding changes, durable STOP, and a full historical
source → acquired entry → delayed preparation → isolated snapshot replay.

## Remaining integration gates

This is an internal preparation seam and offline host check. Live collection of
fresh exit evidence, its provenance, restricted exit signing and a durable exit
submission boundary are **not connected**. A prepared record is not a spend permit.

Next work connects bounded collection and the exit signer/submission path, then
receipt accounting for success, failure and residual holdings. A failed exit must
pay its actual fee without freeing an unresolved position; a replacement requires
separate fresh evidence and remaining attempt budget. Final exposure reconciliation
must precede any release or another entry.

No scanner, observer, notifications, backup timer or fixed study changes. No new
devnet cycle, arbitrary route, mainnet support, wallet-wide allocation authority or
real-money approval is introduced. Strategy profitability remains unproven.
