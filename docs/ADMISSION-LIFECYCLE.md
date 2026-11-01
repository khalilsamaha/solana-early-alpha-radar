# Unified admission lifecycle — November 1, 2026

The durable scoped closure host report passed all 21 expected cases at
08:04:24 UTC on November 1. Exact source replay matched its cases and action
flags. This next increment joins admission, entry, exit and closure into one
read-only historical accounting view. The portable host gate has 24 cases.

## Accounting interpretation

Original reservation caps are displayed separately from the latest verified
scoped accounting. They are history, not extra current holds. The view replays
existing validators rather than trusting the newest table or a public summary.

| Evidence | Report interpretation |
| --- | --- |
| Reserved or signed entry, no settled receipt | Original commitments remain held; acquired quantity and paid fees are unknown (`null`) |
| Acknowledged send or raw receipt without durable application | Unresolved or awaiting accounting; no inferred settlement |
| Applied successful entry | Exact acquired delta and remaining fee commitments held |
| Applied failed entry | Principal held; actual fee charged; no invented acquired inventory |
| Signed or unresolved exit | Last settled commitments remain held; no current balance claim |
| Applied successful exit | Owned residual zero; proceeds and unused fees held until verified closure |
| Applied failed exit | Owned inventory remains held and only verified fees are charged |
| Replayed closure | Historical scoped releases replace those holds; no new allocation authority |
| Missing, malformed, unsupported or contradictory evidence | Current scoped amounts unavailable, never silently zero |

The synthetic example spends 100 source units and returns 96. Closing releases
96 proceeds and 15,998 unused fee lamports, with 10,002 lamports already paid.
The old 100-unit principal cap is not added to proceeds. The 902 protected token
units remain outside this allocation's released amount. Different tokens and
native fee units are never summed into a financial return.

## Read-only behavior

The cooperating wallet lock and a separate SQLite shared read transaction hold
source evidence stable while existing validators open their own read-only
transactions. Connections use `query_only`; a competing writer cannot commit
until inspection finishes. Unknown admission-stage schemas are rejected. The
projection records underlying admission/accounting/closure hashes for comparison.

STOP and expired preparation evidence preserve historical settled accounting;
they do not authorize a new operation. A later conflicting receipt suppresses
current amounts even when an older closure row remains on disk. An old release
never proves current wallet balances or wallet-wide availability.

This is a one-off offline/recovery building block, not a dashboard poller. A
120-second elapsed-time check rejects an over-budget result; it is not a hard
preemptive CPU or filesystem timeout. Local validation does not prove live RPC
latency. No scanner, observer, admission policy or allocator calls this reader.

## Validation and host gate

Seven targeted tests passed: six lifecycle/CLI tests and one full-source
recovery integration. The portable exercise passed all 24 cases. Source hygiene
and diff checks passed. Validation covers read-only connections and
writer exclusion, clock/deadline rejection, conflicting receipts, malformed
closure and changed source identity. The full-source exit/recovery integration
also inspects the final closure before and after STOP and verifies unchanged
source/admission bytes. The tests use disposable journals and synthetic transport.

Fetch the published `feature/admission-lifecycle-20261101` branch and check out
the exact commit supplied with the release. From the running project directory:

```bash
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/admission_lifecycle_cli.py" \
  --output "$PWD/radar-lifecycle-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, 24 cases. The command can take several minutes.
It offers no live action, wallet or submission argument. No RPC, existing private
key, new signature, transaction, production write or allocation release occurs.
Host acceptance: all 24 cases and action flags passed at
2026-11-01 10:10:12 UTC. The public report matched the source self-check.

## Next sequence

After this third increment passes its host check, consolidate the fresh-balance,
durable-closure and lifecycle-view batch with CI. Then validate the complete
separate-transaction lifecycle against actual bounded devnet timing and failure
recovery before considering new allocation. Mainnet and strategy evidence remain
separate gates; this increment is not real-money approval.

The November 1 study capture is already taken, as reported by the user. The next
preservation dates are November 3, 5 and 6; final capture/review opens November 6
at 00:05 UTC / 01:05 Amsterdam. The study and production monitoring are unchanged.
