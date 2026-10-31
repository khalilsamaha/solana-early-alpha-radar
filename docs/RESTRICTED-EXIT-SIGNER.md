# Restricted exit key backend — 31 October 2026

This increment connects the durable exit handoff to an independent Node key
process for the existing controlled devnet scope. It has no live execution CLI,
RPC client, transaction sender, automatic retry or allocation-release path. The
public host command exercises temporary wallets only.

## What the independent process checks

The parent handoff replays the collected raw pool/account/simulation evidence and
current allocation under the wallet lock. The child independently reads the
committed SQLite ledger through a read-only connection, retaining its shared read
transaction until its acknowledgment is saved. It refuses recovery sidecars,
unsafe file ownership/permissions, missing or extra signing events, STOP, expired
original deadlines and an already-existing exit attempt or acknowledgment.

It validates the admission and signing event hashes, preparation/accounting links,
collection hashes and retained devnet genesis. It derives the controlled pool and
account addresses from the saved test-pair plan, reverses the exact account roles,
and reconstructs the unsigned message independently. Quantity must equal the
admission-owned acquired delta; fee commitments are conserved. The fixed compiler
retains its maximum of 1,000 input atoms, 10,000 fee lamports, zero priority price,
existing legacy-token accounts and the fixed devnet program. No generic arbitrary
transaction signing endpoint is added.

The child validates the committed evidence links and restrictive transaction
contract; it does not repeat the parent's complete raw RPC/deployment review.
These local hashes are not RPC-provider attestations. The security boundary is the
trusted local source and private admission directory, not resistance to an attacker
who can replace the code and wallet files under the same user account.

The Ed25519 key must match the expected wallet. A private exclusive
`exit-signer-attempt.json` is fsynced before signing. The child then creates the
exact signature and privately saves `exit-signer-ack.json`. Entry signer files are
never reused. Any interruption after the attempt remains uncertain and cannot be
retried automatically, even if no acknowledgment exists.

## Recovery and snapshots

Recovery validates the existing attempt against the committed signing boundary,
request, preparation and original deadline. It verifies the saved wire before
passing it to the existing acknowledgment recorder. This works after expiry or
STOP without key access and never authorizes a send.

The local private snapshot allowlist includes the two bounded exit backend files.
Isolated restore checks their semantics, including acknowledgment signatures,
while preserving the restored STOP and excluding keys. Orphan acknowledgments,
changed markers and changed wires are refused. Older snapshots without these files
retain their prior projection. No backup service, cloud policy or timer is changed.

## Local validation

All 42 targeted Python tests passed: four backend/integration tests and 38 existing
entry signer, exit handoff and private recovery regressions. The updated public
CLI was rerun after adding the concurrency case; all 27 disposable-key cases
passed. The full-source integration test exercised the actual child process,
saved-ack recovery with the key removed, and isolated semantic restore including
a tampered-marker rejection. Source hygiene and immutable package manifests passed.
The Kali report at 2026-10-31 18:14:04 UTC matched all 27 cases and flags; these are offline integration tests,
not evidence of a transaction submitted to devnet.

## Kali check

After fetching the pinned source provided in chat:

```bash
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/restricted_exit_signer_cli.py" \
  --output "$PWD/radar-restricted-exit-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, 27 cases. It creates two disposable test keys and
two test signatures inside temporary directories, then removes them. Zero real RPC
requests, transactions or production-wallet accesses occur. Upload only the public
`.json.gz` report. No Docker rebuild or service restart is needed.

## Remaining integration

The next [transport increment](EXIT-SUBMISSION.md) binds one devnet send to this
signed exit and supports observation of the original signature without resending.
It is built with an offline host gate pending. Final receipts then need to reconcile
actual fees, residual inventory and allocation release. No new controlled cycle,
mainnet capability or funded pilot is authorized by this self-check. Monitoring,
quote sampling and the fixed November 6 confirmation review are unchanged.
