# Forward comparison and simulation update — 16 October 2026

Entry-context and metadata provenance deployment passed the supplied one-hour live-data check: all 124 eligible signals had valid entry context; 113 had recorded organic/holder provenance and 11 had genuinely absent values. The five sampled watches all returned timely quotes at the primary horizons, but returns remained poor. Capture success does not promote the current strategy.

This release develops two independent work streams while collection continues:

1. `forward-study`: a fixed two-target, three-cohort protocol, bounded source replay/readiness audit, immutable numeric model freeze, and later evaluation without refitting. Sparse failure labels cannot be relabelled merely to make a classifier train. The existing benchmark is preserved. See [commands and interpretation](../forward-study/README.md).
2. `execution-lab`: a persistent simulation-only intent/reconciliation engine with idempotency, ambiguity, balance, limit, stop and restart tests. There is no chain/RPC/signing adapter or live order path. See [run instructions and remaining gaps](../execution-lab/README.md).

No scanner or observer reinstall/rebuild/restart is required. No request, cohort budget, signal threshold, Telegram or backup setting changes. Models are not automatically fitted or activated. The initial host step is the readiness report and offline scenario report, using the same pinned dev checkout.

## Backblaze side note: diagnosis only

The supplied screenshot shows archives growing from 990.2 MB (11 October), to 995.7 MB (12 October), to displayed 1.0 GB files on 13–15 October. It is a file listing, not the cap-usage screen. Verification-marker files are visible for 13 and 14 October; the cropped image does not establish the latest run's final status.

The existing scanner cloud-backup script uploads each archive and then downloads the whole archive to verify SHA-256 and restored SQLite integrity. Thus each new archive approaching 1 GB also consumes roughly that amount of download transfer for one verification pass, before any other downloads/retries. This is a strong explanation for a reported 1 GB daily download cap. It does not prove every backup failed, or that upload failed when download verification was blocked.

Backblaze documents separate daily caps/alerts and daily counter resets at midnight GMT: https://www.backblaze.com/docs/cloud-storage-data-caps-and-alerts . No quota, plan, verification schedule, pruning or backup configuration is changed here. Do not manually repeat a full cloud verification merely to test the cap.

Read-only local status, with zero cloud requests:

```bash
sudo python3 -E -s ~/apps/solana-radar-dev/operations-tools/backup-status.py
```

Compare latest local/cloud completion timestamps and service results. A prior `success: true` can be stale. The next backup decision should be based on those statuses and the exact cap category/value. This development release uses original exports and verified local captures; it needs no cloud downloads.
