# Guarded second controlled devnet cycle

The October 24 Kali reports passed 45 offline checks and prepared cycle 2 after verifying one incoming 20,000,000,000-lamport transfer. The saved wallet balance is 39,824,059,960 lamports; original/acquired test-token balances are 499,999,997 and 500,000,000 atomic units. Historical swap fees remain 10,000 lamports. No transaction was signed or sent during that preparation.

This release connects that immutable preparation to the controlled sender, signer and spending reservations. Actual cycle-2 execution on Kali remains pending. It does not change the scanner, observer, frozen model, study admission rules or backups. No production rebuild or service restart is needed. The frozen study review remains October 27.

## Execution scope

The dedicated wallet and controlled test pool remain fixed. A separate `controlled-cycle-0002` journal contains one entry, one reverse and its own spending database. The original root-level pool, simulation, entry, reverse and accounting journals remain historical evidence. They are not copied, reset or replayed.

- Entry: exactly 1,000 atomic original-token units; minimum output 990; no priority fee; maximum fee 10,000 devnet lamports.
- Reverse: exactly the amount acquired by the new entry, never the background token holdings. It requires that entry's exact finalized receipt and fresh holder/native continuity.
- Reserve 20,000 lamports for the new round trip before entry signing. Historical fees are carried forward separately. Maximum cumulative gross input is 2,000 atomic units and cumulative swap fees are capped at 40,000 lamports. With the historical 10,000, the reserved total starts at 30,000.
- A failed entry consumes its confirmed fee and cannot be retried. A failed reverse leaves exposure visible and has no automatic replacement. Missing/expired/uncertain outcomes retain reservations. Contradictory receipts quarantine accounting.
- Every explicit leg has one durable signing attempt and one application send boundary. Repeating an action returns recorded state, not another transaction. Recovery only observes the recorded signature.

The entry builds a fresh blockhash/message, rechecks the controlled deployment and accounts, simulates the signed transaction and repeats preflight before submission. The original simulation is reverified as expired/unsubmitted; its signed bytes are never reused. Current wallet/token balances must still match the sealed cycle preparation at entry. Additional transfers or account changes require investigation rather than automatic rebasing. Do not top up or use this dedicated wallet during the cycle.

## Independent binding and recovery

The plan and spending journal bind the preparation hash, prior-evidence hash, wallet/pool, historical spending, fixed allocation and starting balances. The Node signer independently checks the preparation seal, fixed cumulative limits and a committed hash-chained SQLite reservation before accessing the key. It signs only the fixed controlled instruction shape. Before submission, the Python guard rechecks plan/signed identity and records the reservation's consumed boundary durably.

Within one wallet-locked operation, historical receipt replay is cached to avoid spending the short preflight lifetime repeatedly verifying the same immutable history. Preparation/seal bytes are checked on each binding lookup; changes fail. The cache is discarded on return/error and never supplies cross-operation approval. The signer separately reads its reservation and preparation. The same-user filesystem remains a trust boundary; someone holding the private key or signed bytes can bypass this application. This is not a mainnet security boundary or wallet-wide spending policy.

The historical position book is not rewritten. New-cycle receipt and reservation reports provide the new accounting; combining it into a broader position inventory remains separate work. Devnet test-token results do not establish route availability, mainnet execution quality or strategy profitability.

## Kali procedure

Fetch and detach at the exact release commit supplied in chat. First run the new self-check: 23 tests using disposable unfunded wallets and synthetic RPC. It does not access the existing wallet or public network.

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/devnet-pool/cycle_execute_cli.py" \
  --output "$PWD/radar-cycle-execution-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

All non-self-check commands require the explicit scope below. `inspect` reads local public evidence without the key or network. `entry` and `exit` require `--allow-devnet-submit`; status/recovery refuse that flag.

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/devnet-pool/cycle_execute_cli.py" \
  --action inspect \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-cycle-two-inspect-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

After the check passes, an explicit `--action entry --allow-devnet-submit` with the same scope sends at most one new entry transaction. `finalized-success` plus its exact receipt is the entry gate. Review that report before the separate `exit` action. Do not chain entry and exit blindly: an exit needs the successful current-cycle entry, and missing evidence is not success.

For an interrupted or uncertain entry, use `--action recover-entry` with the same scope and a new output file. For an interrupted reverse, use `recover-exit`. Neither can send. `status-entry`/`status-exit` replay local evidence and do not refresh balances. Never delete, rename, recreate or edit journals to retry. The root-level `STOP` marker blocks new signing/submission; observation remains available.

Upload only the public `.json.gz` reports. Keep the dedicated wallet directory private.

## Validation and next gate

Tests cover the complete second-cycle entry/reverse, preserved historical files, cumulative accounting, duplicate actions, lost acknowledgement, unresolved and failed legs, changed balances/identity, independent signer refusal without a reservation, preparation changes during an operation, actual process death after the send boundary, root STOP, quarantine and public command-line output. The full existing regression suite must also pass before release.

The next live gate is one controlled cycle-2 entry with its durable reservation and exact receipt. Then verify the reverse and read-only recovery. Research qualification and any explicitly scoped real-money pilot remain separate gates.
