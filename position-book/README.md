# Signed position accounting 1

An offline integration between the existing signed-intent journal and raw signed-token receipt auditor. A position connects a registered entry and its separately registered full exit. Each reservation, intent, boundary and resulting balance update is committed in one SQLite transaction. This component has no signer, private-key reader, transport, service or production adapter.

The default CLI runs ten deterministic cases using temporary ledgers and public synthetic signed transactions. It never opens the dedicated devnet wallet. No install, rebuild, restart, funding or waiting is needed:

```bash
cd ~/apps/solana-early-alpha-radar
python3 -E -s ~/apps/solana-radar-dev/position-book/cli.py \
  --output "$PWD/radar-position-check-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

Upload only the resulting report. Re-running creates fresh temporary synthetic state; it cannot repeat the earlier devnet transaction. Existing output filenames are refused. The report is atomically published with mode 0600.

## Scope and accounting

- One active position, one fixed quote account/mint and wallet, devnet-labelled evidence, standard SPL existing accounts, no WSOL or Token-2022. Full quantity exits only. Creation/closure and rent are explicitly rejected; zero rent is verified rather than blended into fees or profit.
- `reserve` verifies signed identity and the declared prior contract, atomically records both, checks exact cash/native balance continuity and reserves entry principal plus entry and one possible exit fee. Policy and initial balances are immutable. They remain caller assertions, not observed or approved funding.
- `boundary` records an unresolved state before a future sender could act, rechecking local intent age (maximum 15 seconds) and the persistent entry stop. It does not send anything or validate chain blockhash expiry.
- `observe` accepts the original raw signed evidence package, verifies it again, binds it to the stored intent/wire hash, and applies the supported finalized token/fee outcome once. An auditor summary alone cannot change balances. Exit quantity/account/mint/decimals must exactly reverse the acquired position, and every new settled receipt must follow the last reconciled slot.
- Unknown entry/exit outcomes retain reservations and exposure. No reset, cancellation or resubmission API exists. Finalized entry failure consumes the fee and releases principal. Finalized exit failure consumes the fee, keeps the acquired tokens open, and may be followed by a distinct signed exit only if all limits still pass. A failed attempt does not reset cumulative fees.
- Conflicting evidence sets a persistent book quarantine. Unknown evidence cannot erase a final result, and identical finalized outcomes cannot double-count fees or returns. Quarantine blocks further reservations and marks the last reconciled balances unusable for decisions. Other already registered receipts may still be reconciled, without clearing quarantine.
- The entry stop blocks new entry reservations and entry boundaries, while allowing evidence reconciliation and eligible exits. There is no resume command. Stopping a prepared entry leaves its reservation held; no unproven cancellation is inferred.
- Native fees and quote-token gross return stay in different units. `pnl` is **gross quote atomic change**, not net profit or USD. Cumulative gross losses add losing closed positions without offsetting them by winners. The loss limit is an entry circuit breaker after observed losses, not a guaranteed maximum drawdown or stop-loss execution policy. Position principal separately bounds capital at risk.
- The cumulative fee limit includes settled fees and prospective reservation checks. One potential exit fee is budgeted at entry, not an unlimited number of retries. After failed exits, `feeReserveCovered=false` can indicate insufficient remaining budget for another attempt. The implementation never raises limits automatically or claims an exit is guaranteed.

## Persistence and trusted boundary

The developer `Book` API uses a separate `*.positions.sqlite` file in an owned 0700 directory. The existing journal enforces owned 0600 regular files, no symlinks/hardlinks, application/schema identity, FULL synchronous rollback journaling, immediate transactions, clock regression checks, an event cap and reopen-time file cap. New book tables are required; an existing plain intent journal cannot be upgraded silently. Initialization failure is preserved and refused on reopening rather than reset. Status is read inside a consistent transaction.

This is a local trusted-owner ledger, not an authenticated or tamper-proof service. Copying, deleting or editing its state, calling internal SQLite methods or using a sender outside this component bypasses its controls. There is no distributed wallet-wide enforcement. The parent path, local clock and supplied initial balances are trusted; no arbitrary hostile-user filesystem access is supported. Limits are enforced **inside this offline API only**, not in the devnet sender or scanner. These temporary checks need no new backup policy.

Raw evidence signatures authenticate the outer message, not RPC finality, inner instructions, historical token state, cluster identity or router semantics. Separate receipt/accounting consistency does not validate an aggregator swap or authorize execution. A later adapter must bind approved economic limits before signing, validate supported router instructions and genesis identity, independently check freshness/balances, and integrate the durable boundary before sending. ALT, transient WSOL and token extensions require explicit additional contracts.

## Fixtures and tests

`public-fixtures.json` contains four synthetic signed messages for one ephemeral fixture wallet. Its private key was discarded during fixture generation and is not shipped. The fictitious router, slot, mint and balance evidence was never sent to a network. Entry spends 100 arbitrary quote atomic units for 200 asset units; a successful exit returns 80. Synthetic failures charge 5,000 native lamports with unchanged token amounts. These amounts are deliberately tiny test integers, not an approved budget or performance observation.

Tests cover complete entry/exit, failed fees, unknown outcomes, exact signed binding, forged summaries, slot ordering, duplicate final receipts, conflicting outcomes, persistent entry stop, full-quantity/identity/continuity checks, immutable policy, principal and fee caps, loss limits, file constraints, atomic rollback at an event cap, two connections, and actual subprocess death immediately before/after the boundary commit. Host self-check results remain synthetic even when run on the production machine.

## Two closed controlled cycles

`cycles_cli.py` reconciles the first historical round trip and the fixed prepared cycle two into a separate bounded ledger. It preserves the original single-position ledger, keeps verified external credits separate from returns, and never signs or calls RPC. See [the two-cycle accounting guide](../docs/TWO-CYCLE-ACCOUNTING.md) for commands, repeat-import behavior and quarantine handling.
## Scoped reservation reader

The separate `reservation_cli.py` observes the existing two controlled devnet
cycles under the wallet lock using read-only journal connections. It does not
create a book or reserve funds. Its optional quote binding derives commitments
directly from local evidence, while leaving execution and new-cycle approval false.
See [scope and Kali inspection](../docs/LOCAL-RESERVATION-INTEGRATION.md).

## Current-state reverse cost observation

`reverse_cost_cli.py` derives a fresh reference entry quantity, reverses it exactly,
and optionally validates one unsigned reverse simulation using existing actual
tokens and current reservations. It never executes the reference entry or claims
a post-entry round trip. See [scope and host commands](../docs/REVERSE-COST-OBSERVATION.md).

## Independent paired cost scenario

`paired_cost_cli.py` combines two fresh independent unsigned observations through
an internal raw-evidence handoff and models an explicitly selected failed-exit fee
allowance. It retains each quote's clock and rejects mismatched economics, full
quantity or ledger identity. It does not establish a post-entry exit or authorize
spending. See [the scope and host sequence](../docs/PAIRED-COST-OBSERVATION.md).
