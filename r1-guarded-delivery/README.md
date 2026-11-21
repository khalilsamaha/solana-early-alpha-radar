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
