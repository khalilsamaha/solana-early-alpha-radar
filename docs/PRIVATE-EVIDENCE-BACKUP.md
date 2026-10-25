# Private controlled-devnet evidence snapshot

This development-checkout-only tool preserves the closed two-cycle journals and
accounting as a private local directory. It excludes the root `signer.pk8` and the
four `test-token-pair-v1` mint/holder `.pk8` setup keys and the two
`token-lifecycle-v1` source/destination keys without opening them.
Any other private-key file location is refused. Signed transaction evidence remains private: **do not upload the
snapshot, its manifest, or the execution directory.** Only the sanitized public
reports are intended for sharing.

## Scope

- Shares the root execution lock and requires consistent closed two-cycle evidence.
  A pre-existing STOP marker is preserved; other readiness blockers refuse capture.
- Copies supported private files byte-for-byte, preserving the directory layout.
  Directories must be owned 0700, files owned 0600 with one link. Symlinks,
  unexpected file types, SQLite recovery sidecars and caps are refused.
- Caps: 512 files, 64 directories, four nested directory levels, 32 MiB per file,
  256 MiB total. No automatic narrowing, pruning, retry or repair.
- Rechecks source hashes while holding the lock, restores into a disposable local
  directory, checks every SQLite database, then replays the retained two-cycle
  receipts, spending reservations and accounting. STOP is added to the temporary
  copy; no key is present, no network/signing/submission is performed.
- A manifest is written last, only after a successful isolated restore check.
  Failed or interrupted capture directories are retained without a completion seal.
  Existing destinations are never overwritten. Ordinary failures remove temporary
  restore copies; an OS kill/power loss may leave a private `.restore-check-*`
  directory, which is not a completed snapshot.
- Verification takes an existing snapshot and explicit wallet/pool; it does not
  need or open the original execution directory. It verifies bytes and replays
  evidence in a fresh disposable copy, without changing the saved snapshot.

This is a **local evidence backup and restore exercise**, not complete disaster
recovery. It does not back up the signing key, send data off-machine, encrypt the
snapshot, install a timer, or restore an executable wallet. Hashes are corruption
checks, not independent authenticity proofs. All other SQLite files get integrity
checks; semantic execution/accounting replay covers only the fixed two cycles.

Never copy an old snapshot over the active execution root. A valid historical
snapshot does not prove it is current and must not reset spending or submission
history. Production restore, fresh on-chain reconciliation, separate key custody
and encrypted off-machine storage require a later design.

## Host sequence

Use the pinned commit supplied with the PR. No Docker rebuild, scanner deployment,
service restart, sudo, cloud request or change to the frozen study is needed.

From the project directory, run the self-check first:

```bash
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/evidence_backup_cli.py" \
  --output "$PWD/radar-private-evidence-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Then create an owned private parent directory outside both the project and execution
root. Pass a new child as `--snapshot`, and the explicit existing execution directory,
wallet and pool with `--action capture`. Save the returned public report outside
both private directories. Run `--action verify` with that same `--snapshot`, wallet
and pool, omitting `--directory`, in a separate process.

Both capture and verification must report `isolated-restore-verified`. They report
the same manifest hash, no key access, no source mutation, zero network/sign/send
counts, and two closed cycles verified. The self-check reports 17 synthetic cases.
These results do not authorize further execution or qualify a trading strategy.

If a command stops, preserve all source and snapshot files and share its terminal
message. Do not remove STOP, alter permissions recursively, clear journals, retry
execution or delete a failed snapshot to make the check pass.

## Validation

`cd position-book && python3 -m unittest -v test_evidence_backup`

The tests cover exact isolated replay, no key reads/network/source mutation,
permissions and links, existing STOP, concurrent lock refusal, missing receipts,
SQLite sidecars, unsupported files, source/output separation, byte corruption,
manifest traversal, caps, incomplete publication, non-accounting SQLite integrity,
semantic tampering despite updated hashes, sanitized output and fresh-process
verification. The normal source regression discovers these tests automatically.

GitHub runs `scripts/check.sh core` and `scripts/check.sh devnet-pool` as independent
jobs: the expanded sequential suite reached the existing ten-minute job deadline.
No tests are removed. `bash scripts/check.sh` still runs both groups locally.

## Rollback

Return the development checkout to consolidated main `f2e4898700d7e8d265c51710ef9f67c9bda10de1`.
No service or source-state rollback is needed. Preserve completed snapshots and
public reports; they are historical evidence, not a replacement execution root.
