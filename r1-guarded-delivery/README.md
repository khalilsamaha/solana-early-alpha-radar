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

## Recommended pilot retention policy · 21 November 2026

**Keep each complete or quarantined R1B evidence package for at least 90 days.** This gives the project a quarterly review window and time to repeat a restore after the pilot closes. The period is a design choice. The November 21 recovery of historical fixtures establishes a point-in-time result only.

| Decision | Pilot policy |
|---|---|
| Destination and scope | Use a dedicated `r1-pilot-evidence/` prefix in the existing private B2 bucket, subject to destination review. Use a unique object name for each attempt and record the B2 file/version ID. Keep E0 journals, existing backups and provider credentials outside this transfer. |
| Retention clock | For each exact object version, use the B2 upload timestamp in UTC plus 90 × 24 hours as the earliest disposal review. Record both times in the receipt. An ambiguous upload or missing version ID keeps the attempt open for reconciliation. |
| Evidence to keep | Keep the original private package, external digest, byte count, member index, source and verifier identities, transfer intent, and restore receipts through final review. Preserve failed and interrupted attempts with their recorded verdict. Keep compact identity and disposition records through project closeout. |
| Restore and release | On delivery and again at or after day 90, an independent receiving environment retrieves the recorded version without relying on the producer. Verify byte count and SHA-256, replay the matching verifier and compare verdicts. Any failure, unresolved discrepancy or open evidence hold extends preservation. Successful final review makes the package eligible for an explicit owner disposal decision. |
| Budget | Allow zero incremental spend. Before writing, calculate the batch size from the final manifest and verify headroom in the existing allowance for retained versions, pending uploads, operations and both retrievals. Retain local originals if capacity or charges are uncertain. The two historical archives totaled 4,019,855 bytes; live pilot sizing remains open. |
| Activation evidence | Record the exact private bucket and prefix, effective lifecycle and retention rules, existing access for the writer and independent reader, and the available allowance. Review all rules that can match the prefix, including bucket-wide rules. Hold the transfer if current settings permit premature loss or prevent independent recovery. |

B2 lifecycle rules can hide or delete versions. Bucket-level Object Lock enablement is irreversible. This recommendation leaves both mechanisms as configured and calls for reviewing the effective settings before the first pilot write. The 90-day target is an operating policy; evidence of enforced immutability requires separate verification. [B2 lifecycle rules](https://www.backblaze.com/docs/cloud-storage-lifecycle-rules) · [B2 Object Lock](https://www.backblaze.com/docs/cloud-storage-object-lock)
