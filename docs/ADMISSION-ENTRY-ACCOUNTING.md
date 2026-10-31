# Collected entry receipt to same-ledger accounting

This increment records the effects of a collected entry receipt in the existing
private admission ledger. It distinguishes acquired tokens, spent principal,
actually paid entry fees and commitments still held for exit attempts. The record
is not a new allocation, and no funds become available for another entry.

## What is integrated

`position-book/entry_accounting.py` replays the exact admitted message, durable
submission boundary, devnet genesis-bound RPC capture and raw receipt. An
acknowledged send alone, an imported receipt without collector provenance, missing
evidence or a quarantined result cannot create usable accounting.

One settlement row is committed in the same SQLite database. The original admission
and its historical commitment remain unchanged. Repeated application compares the
same evidence and returns the existing row without another fee or token movement.
An independent read-only connection validates the source while a write reservation
excludes other database writers. Receipt validation and insertion therefore cannot
race a cooperating or SQLite writer. A failed insertion rolls back; a committed
row survives process death. Status does not create tables or update the ledger.

| Receipt outcome | Principal | Token ownership | Native fees |
| --- | --- | --- | --- |
| Collected successful entry | Input recorded as spent | Own only the positive acquired delta; exclude preexisting destination inventory | Record actual entry fee; retain unused entry cap and all exit-attempt caps |
| Collected failed entry with fee-only effects | Original input remains held | No acquired position | Record actual failure fee; retain unused caps |
| Missing or unresolved receipt | Original commitment remains held | Unknown; not interpreted as zero | Unknown; not interpreted as zero |
| Conflicting/quarantined evidence | Do not release anything | Existing settlement retained but unusable | Require reconciliation; do not overwrite the previous record |

For the portable success fixture, 100 input atomic units become 98 acquired units.
From the original 26,000-lamport fee commitment, 5,001 are paid and 20,999 remain
held: 20,000 for two exit attempts and 999 of unused entry allowance. These are
synthetic values and accounting conservation checks, not returns or profit.

STOP and expiry prevent new execution but do not suppress accounting for an
existing collected receipt. A successful record remains a historical observation,
not proof that the wallet still has those balances at the current instant.

## Host acceptance

The only CLI is an offline synthetic check:

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/position-book/entry_accounting_cli.py" \
  --output "$PWD/radar-entry-accounting-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, **15 cases**, zero network requests, keys,
signatures or transactions. Temporary fixture databases are removed. Existing
output files are refused. No live directory, wallet, execute or receipt-import
arguments are accepted. Upload only this public self-check report.

All 17 focused regression tests passed locally, including crash/rollback, writer
exclusion, tampered raw evidence, STOP, exact replay and CLI output protection.
Focused regression additionally exercises a disposable independent signer through
the actual source reader, synthetic collector and settlement, including a destination
account with preexisting inventory. No test submits to a real network.

The host report captured October 31 at 04:57:52 UTC matched all 15 cases and flags
exactly. This accepts the synthetic accounting gate; no runtime deployment occurred.

## Remaining integration gates

1. Accept the new [combined recovery snapshot](ADMISSION-RECOVERY.md) host check,
   which preserves the admission ledger and acknowledgment files alongside history.
2. Bind fresh delayed exit preparation to this exact owned quantity, still-held fee
   budget and a new blockhash/deadline. Integrate failed/unknown exits and residuals.
3. Reconcile final ownership and costs before any allocation release or next entry.
4. Complete a separately reviewed deployment and controlled devnet exercise before
   considering mainnet scope. Passing this self-check approves neither a new cycle
   nor a funded pilot.

Scanner, quote observer, notifications, backups and research-study registrations
are unchanged. The fixed availability-study capture/review schedule remains intact.
