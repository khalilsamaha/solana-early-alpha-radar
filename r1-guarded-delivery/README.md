# R1B offline delivery of guarded handoff evidence

The local mirror accepts the six previously reviewed November 17 handoff packages. The case table pins each original byte count, external SHA-256, producer revision and expected verdict. The verifier runs from a disposable export of the exact Git tree for that revision. This preserves reader identity across different publication commit IDs. The package and reader report must match across source and retrieval. A verified quarantine can finish delivery while its handoff remains quarantined.

Use the existing private `handoff/evidence.zip` for the named case, a full local checkout containing the two pinned source trees, the project Python environment and an existing private mirror directory. Commands from the repository root:

```sh
python3 -B r1-guarded-delivery/local_transfer.py rehearse normal-service-exclusion PRIVATE_MIRROR PRIVATE_PACKAGE
python3 -B r1-guarded-delivery/local_transfer.py inspect normal-service-exclusion PRIVATE_MIRROR
python3 -B -m unittest discover -s r1-guarded-delivery
```

The mirror stores a single-use attempt and an exclusive local destination per digest. Each new file is flushed before the next step. Inspection checks intent, object, retrieved bytes, the original reader verdict and the completion receipt. It never writes a transfer receipt. On interruption or refusal, retain the directory for inspection. An existing destination or consumed attempt is preserved.

Budget two additional copies on the mirror filesystem plus receipts, in addition to the original source. The preliminary free-space check covers those two copies; concurrent consumption can still interrupt a write. Reader scratch and replay allocations require separate space. The largest of these six fixtures is 426,617 bytes. The checks cover local process interruption and concurrent invocations under a trusted local filesystem. Power-loss durability across filesystems, production capacity, remote delivery, retention and target-host acceptance remain open.

R1A is on hold pending assessment of an independently managed host. E0 remains blocked with holds preserved. This tool only operates on local fixture evidence.

## Independent restore from delivered archives

On November 21, 2026 at 06:45 CET, both archived November 17 acceptance batches were freshly retrieved from the project's existing off-machine file storage. The receiver used the published source checkout and the retrieved files. It did not need producer-side transfer receipts, a local mirror completion file or access to Kali. Both outer hashes and both member-index hashes matched the published review. The pinned readers recovered the six accepted cases, totaling 1,829,043 package bytes. One complete offline handoff and five quarantined handoffs retained their original verdicts. The earlier, incomplete deadline-after-shutdown attempt is excluded from the first batch.

Run the receiver on the two private archive files, in the order originally accepted:

```sh
python3 -B r1-guarded-delivery/verify_archives.py \
  'acceptance(20261117-134657).zip' 'acceptance(20261117-135516).zip'
```

The command emits a single integrity receipt only after both batches pass. It operates on the retrieved files already present at the receiving end. Storage location and retrieval time need separate provenance. Its report includes each archive and index digest, the reviewed reader tree, and each case's digest, byte count, verdict and reader report digest. The November 21 canonical receipt SHA-256 is `9c24f0a60f032ece3af68aec563b3366c1f6ca740629ed7535ca3b84e36a3218`. The historical archive inputs are 1,514,293 and 2,505,562 bytes. Temporary private replay copies are discarded after inspection.

**Preservation disposition.** Independent recovery of these historical fixtures is verified at that observation. A transfer from the future pilot producer, access and retention policy at its destination, and recovery after the agreed retention interval remain open. A future bounded delivery needs a named private destination, a retention term, a permitted storage budget, and a receiving identity able to retrieve independently of the source. Retain failed or interrupted attempts for reconciliation. The current evidence supports no claim of continuous coverage, future availability or live pilot readiness.

## Owner-approved pilot retention policy · 21 November 2026

**Keep each complete or quarantined R1B evidence package for at least 90 days.** This gives the project a quarterly review window and time to repeat a restore after the pilot closes. The owner approved this term, the dedicated prefix, independent restores and zero incremental spend on November 21, 2026. The November 21 recovery of historical fixtures establishes a point-in-time result only.

| Decision | Pilot policy |
|---|---|
| Destination and scope | Use a dedicated `r1-pilot-evidence/` prefix in the existing private B2 bucket, subject to destination review. Use a unique object name for each attempt and record the B2 file/version ID. Keep E0 journals, existing backups and provider credentials outside this transfer. |
| Retention clock | For each exact object version, use the B2 upload timestamp in UTC plus 90 × 24 hours as the earliest disposal review. Record both times in the receipt. An ambiguous upload or missing version ID keeps the attempt open for reconciliation. |
| Evidence to keep | Keep the original private package, external digest, byte count, member index, source and verifier identities, transfer intent, and restore receipts through final review. Preserve failed and interrupted attempts with their recorded verdict. Keep compact identity and disposition records through project closeout. |
| Restore and release | On delivery and again at or after day 90, an independent receiving environment retrieves the recorded version without relying on the producer. Verify byte count and SHA-256, replay the matching verifier and compare verdicts. Any failure, unresolved discrepancy or open evidence hold extends preservation. Successful final review makes the package eligible for an explicit owner disposal decision. |
| Budget | Allow zero incremental spend. Before writing, calculate the batch size from the final manifest and verify headroom in the existing allowance for retained versions, pending uploads, operations and both retrievals. Retain local originals if capacity or charges are uncertain. The two historical archives totaled 4,019,855 bytes; live pilot sizing remains open. |
| Activation evidence | Record the exact private bucket and prefix, effective lifecycle and retention rules, existing access for the writer and independent reader, and the available allowance. Review all rules that can match the prefix, including bucket-wide rules. Hold the transfer if current settings permit premature loss or prevent independent recovery. |

B2 lifecycle rules can hide or delete versions. Bucket-level Object Lock enablement is irreversible. The approved policy requires review of the effective settings before the first pilot write. The 90-day target is an operating policy; evidence of enforced immutability requires separate verification. [B2 lifecycle rules](https://www.backblaze.com/docs/cloud-storage-lifecycle-rules) · [B2 Object Lock](https://www.backblaze.com/docs/cloud-storage-object-lock)

**Destination review status at approval.** The [previous B2 rehearsal](../docs/R1-SESSION-BACKUP-20261111.md) identifies the intended bucket as `solana-radar-backups-redeye-2026`. That bounded round trip used `r1-rehearsal/`. The proposed pilot destination in the same bucket is `r1-pilot-evidence/`. Current bucket privacy, applicable lifecycle and Object Lock settings, writer and independent-reader access to the pilot prefix, and allowance for the final pilot manifest remain unverified. The first pilot upload is pending these checks. Its version-specific retention clock begins at upload.

### Read-only destination preflight

Run from a reviewed research checkout on Kali. The existing rehearsal configuration identifies the remote and bucket. This lookup reads bucket lifecycle metadata with the existing identity. Pass no backend options that set lifecycle parameters. The checker reads JSON from stdin and prints effective rule values without object names, bucket contents, or credentials.

```bash
set -o pipefail
sudo /usr/bin/timeout 30s /usr/local/bin/rclone --config /etc/solana-radar/rclone.conf \
  --retries 1 --low-level-retries 1 backend lifecycle \
  radar-b2:solana-radar-backups-redeye-2026 |
  python3 -I r1-guarded-delivery/retention_review.py
```

Exit 2 means hold. Missing metadata and denied access stay unknown. Keep the exact observation time and source privately. Match every bucket-wide, ancestor, exact and narrower prefix rule; the smallest matching non-null value for each action applies. A hide-only rule can leave the exact version readable by ID. A delete-after-hide rule also matters when a version is overwritten or manually hidden. A matching automatic hide-and-delete path requires owner review even beyond day 90 because a discrepancy can extend preservation. Unfinished-upload cancellation is reported separately from completed-version retention. Exceptions based on Object Lock require separate review of effective version protection. [B2 lifecycle semantics](https://www.backblaze.com/docs/cloud-storage-lifecycle-rules) · [Read-only rclone lookup](https://rclone.org/b2/#lifecycle)

For a full desk review, pass `--review PRIVATE_REVIEW.json`. Supply only reviewed values. Omit unknowns. Use the exact `bucket` and `prefix`. The boolean fields are `bucket_private`, `object_lock_settings_reviewed`, `writer_can_create_unique_objects`, `independent_reader_can_restore_version_by_id`, `no_manual_hide_or_overwrite_before_owner_release`, and `zero_incremental_cost_for_operations_and_retention`. The last field covers operations, both restores, the retention term and any extension that would require renewed budget review. Supply integer `final_manifest_bytes`, `available_storage_bytes` net of existing commitments, and `included_retrieval_bytes` available for both full restores. Scope each value to this pilot destination and planned billing periods, and retain its supporting observation. A result of `reported-preflight-conditions-met` describes the supplied evidence only. The command has no B2 client and grants no upload or disposal authority.
