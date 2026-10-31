# Combined admission evidence recovery

This increment extends local recovery coverage to the fixed admission sibling as
well as the original closed two-cycle journals. The earlier snapshot tool remains
available for its original scope; it does not silently gain admission coverage.

The new `position-book/admission_recovery.py` takes one private snapshot containing:

- The supported historical source evidence, with the seven known `.pk8` key files
  excluded without opening them.
- The fixed sibling's `entry.admission.sqlite` and any present
  `signer-attempt.json` / `signer-ack.json` files.
- A manifest written last, after byte checks, SQLite integrity and isolated
  semantic replay have succeeded.

The historical spending head and cycle binding must match the admission's original
source binding. Verification replays signed acknowledgment/message identity, the
submission boundary, collected receipt evidence and entry accounting where present.
An incomplete signer response or unknown submission remains unresolved. Valid
quarantined evidence remains quarantined; a passed restore check never clears it.
Invalid, unsupported or contradictory source records fail closed without a seal.

The tool does not apply a saved acknowledgment, collect missing RPC evidence, settle
an outstanding receipt or modify reservations. It preserves the state actually
present. The public report distinguishes transport and settlement state from
successful snapshot verification.

## Isolation and bounds

The cooperating wallet lock covers both sources. A read-only SQLite transaction
also holds a shared lock on the admission database during copying. Source hashes
are checked again before completion. Existing recovery sidecars, symlinks, hard
links, non-private permissions and unexpected sibling files are refused.

Historical files retain their existing bounds: 512 files, 64 directories, four
nested levels, 32 MiB per file and 256 MiB total. The admission sibling allows only
three fixed names: its database up to 64 MiB, attempt up to 1 KiB and acknowledgment
up to 4 KiB. Combined size is capped at 320 MiB plus 5 KiB. No pruning, automatic
narrowing, retry or repair is performed.

Replay uses a disposable copy with STOP added before semantic inspection. All
journal connections are read-only. The snapshot can be verified without opening
the original source. No active restore destination is accepted. Normal failures
remove temporary replay directories; process termination or power loss can leave
an incomplete private directory, which must be preserved for investigation.

Snapshots contain private signed transaction evidence. **Do not upload a snapshot,
its manifest or the execution/admission directories.** Share only the public report.
Checksums detect corruption, not malicious replacement of all evidence. Historical
consistency does not prove current balances or that a snapshot is the latest.

## Host acceptance

All 19 local recovery tests passed on October 31, 2026. The Kali report captured
at 05:26:57 UTC passed all 19 actual cases. Its formatter also listed the non-test
`test_key` attribute as passed (no key value); the next release corrects that case
list using callable test discovery.

First use the exact commit supplied in chat and run the default self-check:

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/position-book/admission_recovery_cli.py" \
  --output "$PWD/radar-admission-recovery-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, **19 cases**. This self-check generates disposable
signed test fixtures in temporary directories. It does not access the existing
wallet, use a network, submit transactions or modify production services. The
existing scanner, quote observer, backup timers and fixed study remain unchanged.
No sudo, Docker rebuild or restart is needed.

After acceptance, `--action capture` supports an explicit existing `--directory`,
`--wallet`, `--pool` and new private `--snapshot` destination. It requires both the
historical source and its admission sibling; it never creates a missing admission.
`--action verify` accepts only the saved snapshot and explicit wallet/pool, with no
source directory. Both publish `isolated-admission-restore-verified` only after the
checks pass. A production capture is not required for this synthetic integration
stage because this new admission path has not been deployed to the host wallet.

Both capture and verify must write their public report outside all private source
and snapshot directories. Existing reports and snapshot destinations are refused.
No command restores into active state, removes STOP or re-signs/re-sends anything.

## Next gates

1. Validate the new [fresh delayed exit preparation](ADMISSION-EXIT-PREPARATION.md)
   on Kali, then connect bounded live collection and restricted exit signing.
2. Integrate exit execution/recovery, failed fees and residual ownership without
   prematurely releasing funds.
3. Reconcile final exposure before any next entry; separately review deployment
   and controlled devnet acceptance.

Local evidence recovery is not off-machine disaster recovery or signing-key
custody. Those controls, wallet-wide allocation authority and mainnet support remain
separate work. This increment does not enable a new cycle or real-money pilot.
