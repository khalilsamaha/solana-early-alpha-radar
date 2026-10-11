# Launch context study — 11 October 2026

This update builds a read-only comparison of launch information available before each recorded research signal and its subsequent original-pool price observations. Production collection continues. No installer, scanner rebuild, service restart, extra provider request or notification is needed.

## What is confirmed

The supplied Kali output confirms deployment of launch foundation commit `2dd705df52327e33e5837c31586794c149e3de30`, readiness and zero restarts in the short check. The first audit contained 38 received creations: all had a reported creation trader, none had a reported creator. Thirty-seven had a metadata URI hash. The quote-ledger local/cloud backup completed with restore integrity verification. These are initial operational checks, not sustained-health or trading-performance evidence.

## What the study answers

For Fast30, baseline and early-activity research entries, the report compares:

1. Whether the **reported creation trader** appeared in other retained launch receipts in the preceding 24 hours.
2. Whether the **same metadata URI hash** appeared on other retained launches in that interval.

Each comparison has zero, one-or-more and unknown groups. The current mint and equal-time or later receipts are excluded from prior counts. Matching launch records received after a signal remain explicitly unavailable for that signal. Creator and trader roles stay separate. A zero count is not proof of a first-ever launch; URI equality does not authenticate metadata content or imply fraud.

Groups remain separate by cohort, recorded Fast30 follow-up admission/policy, and entry-time liquidity (at least $5,000, below, unknown). The threshold is a descriptive stratum, not a new trading filter. All contrasts are exploratory. `launch-study/protocol.json` and its SHA-256 identify the analysis definition; they do not register a future trading strategy.

At 30, 60, 120 and 300 seconds after each signal, the report retains observed, missing, gapped, invalid, pending and overdue outcomes. It checks entry/outcome identity, original pool, checkpoint timing and return arithmetic. No timely observation after the checkpoint tolerance becomes overdue; an explicit missing record stays missing. Pool transitions do not become synthetic returns.

Only observed, valid, ungapped original-pool prices enter return summaries. Full state counts remain beside them. Mean, median, 5th/95th percentiles, losses of at least 50%, and mean excluding the single best result show dispersion and outlier dependence. These are gross sampled price changes. They do not represent quotes, fills, fees, a portfolio or independent trials. Fixed UTC hourly blocks and distinct mint/trader counts expose some dependencies; they do not remove them.

## Run on Kali

Fetch the development branch and check out the exact commit supplied in the release message. Work in `~/apps/solana-radar-dev` for Git commands; keep production in `~/apps/solana-early-alpha-radar`.

From the production project directory:

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/launch-study/run-report.sh --hours 6
```

Upload the `radar-launch-study-*.json.gz` path printed at the end. A short first report can validate joins immediately. Collection need not stop or wait overnight. Entries before registry registration are excluded, so the actual window can be shorter than requested. Zero matched entries is a valid coverage finding, not a performance result.

The existing quote and pool/exit reports remain the execution-evidence lane. This report deliberately does not join baseline research IDs to alert IDs or extrapolate quote results to unquoted entries. The next development step can join qualified study cases to exact quote evidence with full admission/failure denominators after inspecting actual launch coverage.

To refresh feature availability using the corrected reporter:

```bash
bash ~/apps/solana-radar-dev/operations-tools/run-launch-audit.sh --hours 6
```

The health snapshot has no persisted capture timestamp in the scanner. Audit format 2 now labels `snapshotAt: null` with `timestampState: not-stored-by-scanner`, includes the report's read time, and preserves last market/loop clocks. Read time must not be interpreted as the health object's historical timestamp. The existing backup installation remains unchanged.

## Offline use and bounded reads

```bash
python3 launch-study/report.py --database /path/to/completed-backup.sqlite \
  --hours 6 --output /path/to/new-report.json.gz

python3 launch-study/report.py --input /path/to/report.json.gz \
  --output /path/to/replayed-report.json.gz
```

A direct database read uses the current host clock as cutoff. For an older backup, its recent-window entries may be absent; this command does not infer the backup's historical cutoff. Replay the stored report to preserve its cutoff and source identity exactly.

The collector opens SQLite read-only in a pinned transaction, with a 10-second read budget, 64 MiB WAL-growth ceiling, 128 MiB cumulative source-JSON budget, at most 6,000 entries, four outcomes per entry, and 100,000 streamed launch records. It reads indexed entry kinds and exact outcome IDs; it never reads snapshots, candidates or outbox. Large or malformed records, missing schema/registration, source replacement, and exceeded limits stop publication. If the entry/read cap is reached, retry with `--hours 1`; do not raise caps as a first response. Narrowing the signal window still needs up to 24 hours of prior launch context and might not resolve a registry byte cap.

The final gzip is created privately (0600), owned by the invoking user under sudo, and published atomically without overwriting prior reports. Decompressed reports are limited to 64 MiB. Reports include the projected input rows needed to replay the calculation, an input-read digest, source identity, actual cutoff and partial-lookback evidence. The digest identifies the read bytes; it is not an external attestation of source completeness. Repeated or overlapping exports are not new independent data.

A read-only transaction can still consume CPU/I/O and briefly pin WAL history. It has bounded cost, not zero cost. No new timer is installed: use a first manual report to validate real coverage before scheduling more work.

## Development sequence and promotion gates

| Step | State | What decides the next move |
| --- | --- | --- |
| Stable scanner, backups, paper/quote evidence | Deployed, initial launch/backup checks supplied | Continue sustained-health and retention monitoring |
| As-of launch context and outcome report | Implemented and regression-tested; host report pending | Match coverage, unknown fields, pool/timing validity and group counts |
| Candidate feature and execution comparison | Next | Inspect descriptive groups and exact quote admission/failures, without selecting a winning exit retrospectively |
| Frozen forward trial | Not selected | Define one hypothesis, sample/dependence plan, costs, primary horizon and failure gates before evaluation |
| Execution controls and funded pilot | Not ready | Demonstrated evidence plus separate execution engineering and explicit funded-trial approval |

Current data do not establish a profitable edge. This development shortens the path to an informed accept/reject decision; it does not supply a real-money start date.

## Collector correction — 11 October 2026

The first host attempt stopped with a generic SQLite `OperationalError`, so its exact cause was not captured. Local query-plan inspection reproduced a performance defect: the combined `kind + id IN + at` outcome query can select the time-range index and scan historical outcomes for every entry. Collector `launch-study-1.0.1` instead performs four single-key equality lookups using the existing unique `(kind,id)` constraint and applies the cutoff to each returned row. It does not add an index, modify the database or extend the read budget. A regression fixture with 50,000 unrelated historical outcomes verifies bounded lookup work.

SQLite failures now disclose a safe classification, read stage, elapsed seconds, entry/outcome counts and numeric error code. Timeout, lock/open/permission and schema/query failures are distinct; SQL, payloads and paths are omitted. This corrects a reproduced reader defect, but the generic host error alone does not prove that defect caused the host failure. Retry with the corrected collector; retain any new diagnostic.
