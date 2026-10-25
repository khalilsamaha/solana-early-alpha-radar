# Consolidated local operational review

This release adds a one-shot local health report. Run it from the existing live project, using the separate development checkout. It does not install anything, restart services, contact cloud/market providers, send notifications, sign, submit, or evaluate the frozen study. The controlled two-cycle devnet rehearsal remains closed.

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/operational-review/run.sh
```

Upload only the printed `radar-operational-review-*.json.gz` public report. Keep `.env`, keys, private journals, experiment artifact and captured quote rows private. The helper reads the dashboard token locally for two fixed loopback endpoints; neither the token nor raw errors/logs appear in the report. Run as the normal project user; the wrapper requests sudo only for local Docker/service/backup/observer inventory. Allow up to several minutes on a slow host.

## What is checked

- Scanner readiness, last market/loop ages, provider states, heap use, statistics-worker errors and event-loop timing. It does not request `/api/stats` or candidate/research endpoints.
- Host/container source hashes against the existing engineering release manifest, container health/restart count, observer installed/configured/self-reported versions.
- Docker, containerd, cron, observer and research/backup timer states; local disk use.
- Quote observer polling, halt and cooldown metadata only, using a bounded read-only SQLite transaction. It does not scan signal, probe or outcome rows.
- Local and cloud backup status records independently. A failed shared service does not erase a verified local snapshot. A historical cloud success does not prove current off-machine recovery.
- Frozen artifact/registration integrity and at most eight capture indexes. Requested intervals are merged and interior gaps listed. Chunk existence is checked; chunk contents/hashes, predictions, labels, model performance and qualification are not evaluated.

`observed-ok` means the implemented point-in-time checks have no warning/error findings. It is not proof of sustained uptime, strategy qualification or funded trading readiness. Unavailable evidence is reported explicitly. Counters and pending notifications require comparison over time; they are not automatically a current incident. Missing notification counters stay unknown when the notification object is unavailable.

Operational thresholds are scanner loop age 60 seconds, market age 120 seconds, observer poll age 60 seconds, backup finish age 36 hours, preservation lag 48 hours, heap usage 80%, and disk use 85% warning/95% error. These are report thresholds only, not scanner settings or changes to the research protocol. A future timestamp cannot pass as fresh. Backup age uses the recorded finish time, not merely file modification time. Worker cache age is not treated as scanner failure because idle statistics need not refresh.

## October 28 checkpoint and evidence preservation

October 22 through October 28 spans **seven distinct UTC dates**, not seven full 24-hour periods. Prefer late October 28 in Amsterdam so more of the seventh date has been observed. The existing 200-label, seven-date and other cohort/target guards remain unchanged; some groups can still be insufficient. Do not lower gates or refit to force qualification.

The preserved window ending October 25 at 00:00 UTC must overlap later captures. A final 72-hour capture late October 28 would otherwise start later on October 25. **Run this capture-only command once on October 26** to bridge the windows:

```bash
bash ~/apps/solana-radar-dev/operational-review/preserve.sh
```

It verifies the existing registration, preserves another bounded 72-hour local capture, and never runs model evaluation. Run one preservation at a time; existing captures are never deleted or overwritten. Stop and report a cap error rather than deleting evidence. No Backblaze transfer is performed. Capture windows show what was requested, not uninterrupted collection or complete outcomes.

Keep the existing final review command for October 28, after checking preservation coverage. It combines preserved captures with the final fresh capture and retains the frozen artifact and guards. A positive research result would still require separate execution-cost and mainnet-specific work before any funded pilot.
