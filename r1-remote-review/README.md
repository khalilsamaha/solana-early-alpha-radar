# Read-only retained transfer reconciliation

This reader validates a local retained control directory from `r1-remote` without
contacting B2, loading credentials, creating source locks, writing source evidence,
retrying transfer or restoring a service. It opens the existing lock without
creation and refuses an active owner. Independent replay writes only disposable
temporary copies, which are removed. Its CLI prints a result to stdout and exits
0 for verified retained completion or 2 for unresolved evidence. No output file is
written into the control directory.

Validation binds the exact accepted report and package, fixed destination intent,
source hashes, upload observation, downloaded bytes, both complete restored trees
and terminal receipt including the three ordered command observations. Additional
files, failures, missing/partial completion, changed identities, quarantine erasure,
links, active locks, unexpected tree members and altered restored bytes refuse
verification. Inventory is capped at 96 entries, eight levels, 4 MiB total and
1 MiB per file. Source and retained evidence are checked again before return.

`recorded_completion_verified` means the retained bytes and records reconcile.
It does NOT authenticate who wrote them or independently attest that a remote
request happened. `remote_observed_now`, `remote_preservation_verified` and
`retention_verified` always remain false. A fabricated coherent command history
cannot be distinguished from the real one using local integrity hashes alone.
Quarantined shutdown evidence retains `manual_reconciliation_required: true` even
when transfer completion verifies. Complete cleanup-failure evidence is not a
successful measurement result. Missing or ambiguous evidence remains unresolved;
no remote absence or deletion is inferred.

Read a retained attempt:

```sh
python3 -E -s -B reconcile.py --control-directory /absolute/private/attempt
```

First validate the new reader on Kali with `check_reconcile.py`. It requires the
original delivery report and three fixed synthetic packages, just like the prior
offline check. It runs 18 accepted adapter checks and 17 reader checks, using
mocked B2 commands only. Expected status:
`offline-remote-reconciliation-passed-b2-pending`.
Upload `report.json` and `validation.log`, including available failure diagnostics.
No sudo, Docker, credentials, cloud operation or regenerated capture is needed.

This is additive: `r1-remote`, `r1-delivery` and their source pins are unchanged.
Kali acceptance precedes a separately scoped actual receipt-complete B2 transfer.
No upload entry point is exposed by this reader. Actual remote delivery, ongoing
retention, production rollout, provider/exposure acceptance and the full R1 gate
remain outstanding. The five-working-day engineering cap is not extended.
