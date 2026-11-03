# Controlled devnet command interface — November 3, 2026

The accepted host verification-reuse report passed seven checks and nineteen
stages. It retained original deadlines and lost-response recovery, with 8 verifier
processes for 64 signature checks. Sender source replay measured 267.165 ms versus
876.113 ms in the earlier sample; post-collection time measured 867 ms versus
1,519 ms. These synthetic observations support testing the connected path, not a
live latency guarantee or a profitable strategy.

This third increment after PR #72 adds a standalone command interface around the
existing connected entry, settlement, exit and closure functions. The scanner,
quote observer, Telegram, study, backups and services remain unchanged. No live
action was performed during development. Source publication does not install or
activate any service.

## One explicit action per command

| Action | Required opt-ins | Maximum RPC attempts | Behavior |
|---|---|---:|---|
| `check` (default) | None; rejects operational scope | 0 real | Disposable-key connected lifecycle and command-boundary tests |
| `status` | Explicit directory, wallet and pool | 0 | Read-only source/admission replay; no key inspection |
| `entry` | Signing + submission; explicit fee caps | 25 | Fresh collection, durable admission, one signature and at most one send |
| `recover-entry-signature` | Reconciliation | 0 | Record the existing signer acknowledgment; never sign or resume a send |
| `settle-entry` | Reconciliation | 4 | Observe the recorded signature and apply entry accounting; never prepare an exit |
| `exit` | Signing + submission | 25 | Fresh exit evidence, restricted signing and at most one send |
| `recover-exit-signature` | Reconciliation | 0 | Record an existing exit acknowledgment without the key |
| `settle-exit` | Reconciliation | 4 | Observe the existing exit and apply accounting; retains closure commitments |
| `close-exit` | Reconciliation | 8 | Receipt accounting plus fresh balances and scoped closure, when eligible |

All operational actions require `--directory`, `--wallet` and `--pool`. Existing
validators bind them to the dedicated devnet wallet, controlled pair/pool and raw
private journals. There is no endpoint option, mainnet mode, report importer,
replacement/refresh action, new-cycle action or retry loop.

Signing and submission each require their own exact flag:
`--allow-private-key-signing` and `--allow-devnet-submit`. Reconciliation actions
require `--allow-reconcile` and reject signing/submission flags. They can append
acknowledgment, receipt, accounting or closure records but cannot send. `status`
rejects every write opt-in and uses read-only journal connections. STOP is
reported and never cleared. Partial or empty operational artifacts are occupied,
not permission to create another entry. The local vacant-slot observation does
not inspect current chain balances or establish spending approval.

Entry requires all three fee parameters: `--maximum-exit-attempts` (1–3),
`--maximum-exit-fee-lamports` (positive, at most 10000), and
`--maximum-total-fee-lamports` (positive, at most 40000 and strictly greater than
the exit commitment). Existing raw-cost validation additionally checks actual
entry fees and funding. The later actions cannot replace those caps. These are
fee limits, not a user-selectable token amount; the existing controlled message
and pair rules still determine principal.

## Reports and recovery

Reports are exclusively created with mode 0600. Existing reports are not
overwritten, and reports cannot be published inside source or fixed handoff
folders, including through symlinked parents. Public projections allowlist scalar
state/timing fields, atomic accounting amounts and receipt/accounting identities;
raw replies, signed transactions, key material and exception text are excluded.

An exception can happen after a commit or transport attempt. The failure report
therefore leaves the result unknown and never asserts zero effects. A report-write
failure also does not roll back a transaction. Preserve all private journals and
inspect `status`; do not rerun `entry` or `exit` to retry. A signed-but-unsent slot
cannot be resumed through recovery. Such a case needs separate inspection; this
interface does not reset or discard it.

Unknown, failed, quarantined and late execution results exit 2. Even exit 0 on an
RPC acknowledgment does not establish finality, economic success or permission
to run the next transaction. Review the report and separately choose the matching
receipt/accounting action. No command automatically proceeds to the next stage.
A completed scoped closure does not grant a new allocation or another entry.

## Host acceptance for this increment

First run the pinned checkout and the offline check supplied in chat:

```bash
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/controlled_acceptance_cli.py" \
  --output "$PWD/radar-controlled-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-acceptance-passed`, eight boundary checks and nine connected
lifecycle checks. The actual functions run through the new dispatcher with
synthetic transports and disposable keys. Both deliberately lost send responses
remain unknown until receipt recovery; lost closure recovery remains idempotent.
Five routed calls are recorded: entry, entry settlement, exit, initial closure,
then repeated closure recovery. Temporary source and keys are removed.

Then run the read-only `status` command provided in chat against the dedicated
existing rehearsal scope. A consistent vacant source is reported as
`local-scope-consistent`; an existing admission is replayed as lifecycle evidence.
Neither result is a live execution approval. Upload both public reports. No Docker
rebuild, service restart, airdrop, signing or send is required by these two commands.

## Local validation

Seventeen command/integration tests passed, including the complete offline CLI,
real-source vacant and occupied status, partial journals, incorrect scope and
symlinks, output protection, report-write failure after an action, conservative
exit codes, policy limits and repeated-entry refusal. Both partition checks and
tracked-source hygiene passed. Host acceptance passed on November 3: the 06:10:18 UTC report passed all eight
boundary and nine connected checks. The 06:10:19 UTC status found a coherent
closed historical source, no occupied admission slot and no STOP flag; it made
zero network requests and did not inspect the key or current funding.

## Remaining sequence

Consolidate the three host-accepted increments with full CI
under the agreed workflow. The next operational milestone is a separately chosen
controlled devnet entry and subsequent receipt/accounting review, followed by a
separately collected exit and scoped closure. No live execution commands are part
of this release's acceptance instructions.

The November 3 study capture is completed as reported by the user. Preserve
November 5 and 6 captures and review November 6 at 00:05 UTC / 01:05 Amsterdam.
Economic selection, realistic execution outcomes and a capped real-money pilot
remain separate gates; this command interface does not establish profitability.
