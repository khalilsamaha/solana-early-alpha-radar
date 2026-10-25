# Reconcile the two closed devnet cycles

The October 25 host reports show cycle two finalized both legs: 1,000 original atomic units acquired 998 units, and the exact 998-unit reverse returned 997 original units. Cycle-two swap fees were 10,000 lamports; cumulative swap fees across the two cycles were 20,000. Recovery returned the stored final receipt without network requests or resends. The refused unsigned entry was preserved.

This release adds historical accounting for those two closed cycles. It does not initiate a third cycle. The scanner, observer, trading rules, spending caps, backup jobs and October 27 frozen-study review are unchanged.

## Evidence and storage

`position-book/cycles_cli.py` reads the dedicated private devnet journals under the existing execution lock. Public uploaded report summaries are not accepted as source. The importer replays the exact signed receipts and their retained RPC evidence, validates the sealed cycle preparation and funding proof, validates the unsigned replacement archive when present, and checks cycle-two receipts against the durable spending ledger.

The original `controlled.positions.sqlite` holds one acquisition and must not be overwritten with a different entry. The new bounded `controlled.two-cycle-positions.sqlite` at the wallet root stores a complete two-position snapshot and its hash chain. Source journals, the first position ledger and spending ledgers are not modified. No private key, RPC request, signature or submission is needed. Root STOP does not block historical accounting.

The two closed positions have distinct entry and exit signatures. Cross-cycle token balances must agree. Native funding credits between cycles are verified separately from swap fees and token changes. Setup costs, rent and unrelated earlier wallet activity are outside the totals. Current wallet balances are not queried or claimed.

A repeat imports the same snapshot without appending another event or accumulating fees again. Changed or missing evidence after an accepted import appends a quarantine state that preserves the last accepted historical totals, marked unusable. Restoring the files does not automatically clear quarantine. Invalid source before the first import creates no accounting book. Wrong explicit wallet or pool is refused without poisoning an existing book. Interrupted transactions roll back; a complete empty database can be resumed. Corrupt or ambiguous storage is refused without deleting it.

## Commands

Use the exact pinned release commit supplied in chat. No production rebuild, restart, sudo, devnet funds or submission permission is needed.

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/position-book/cycles_cli.py" \
  --output "$PWD/radar-two-cycle-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"

python3 -E -s "$HOME/apps/solana-radar-dev/position-book/cycles_cli.py" \
  --action sync \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-two-cycle-accounting-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Run sync a second time with a different output filename to demonstrate idempotency. The expected first successful import is `closed`, `ledgerChanged: true`, one event. The second is `closed`, `ledgerChanged: false`, still one event. Expected totals from the reviewed host evidence: two closed cycles, 2,000 gross original atomic units, zero residual acquisition, 20,000 lamports confirmed swap fees and zero reserved fees. All token return totals are computed from the actual retained receipts. The verified funding credit is not profit.

If the command stops or reports quarantine, preserve all journals and send only the public report or terminal output. Do not remove a ledger to clear its history. Self-check uses disposable unfunded synthetic fixtures and may take a few minutes; it does not access the provided live wallet directory.

## Verification and limits

Regression cases exercise repeat and fresh-process import, fee/funding reconciliation, byte-for-byte source preservation, absent keys, blocked network access, lost evidence, changed receipt summaries, archive/spending-ledger tampering, wrong identity, lock contention, unsafe files, changed accounting hashes, incompatible ledgers, interrupted commit, immutable closed snapshots and clock regression.

This is a fixed two-cycle historical projection, not a general trading portfolio or a mainnet execution approval. Local file ownership, shared locking and retained RPC evidence remain trust assumptions. Devnet token arithmetic does not establish a profitable market strategy.
