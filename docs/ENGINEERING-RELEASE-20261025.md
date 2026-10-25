# Engineering consolidation — 25 October 2026

This is a source consolidation of PRs #45–54, followed by documentation and a
release manifest. It preserves their implementation exactly. The purpose is to
replace the development branch chain with one reviewed base for later work.

## Release boundary

| Included | Scope |
| --- | --- |
| Frozen forward experiment | Private artifact verification, retained capture merging, fixed later evaluation; no refitting or model activation |
| Controlled devnet risk | Durable reservations before signing, exact cycle binding, cumulative entry/fee caps and retained unresolved exposure |
| Recovery | One explicitly bounded unsigned replacement, original archive retained, no automatic retry or resend |
| Accounting | Exact receipt continuity across the two fixed closed cycles; idempotent historical ledger |
| Readiness | Local receipt/spending/accounting/STOP inspection with read-only database connections |

The consolidation adds no runtime behavior. Scanner, quote observer, research
collector, market rules, provider quotas, backup jobs and installed services are
unchanged. It adds no mainnet support, wallet-wide spending enforcement, third
cycle, automatic trade or live-money approval.

`releases/engineering-20261025.json` records the prior main, included source head,
source tree, ten PR heads, unchanged component trees and SHA-256 values for the
non-documentation files introduced or changed by the chain. Historical package
manifests remain intact. Private model artifacts, capture data, wallet material,
transaction reports and host journals are not release assets.

## Verification and merge procedure

The source head `b9504ebc422543d4a7b73e619aeb3ebdb9942781` passed 1,453 offline
regression tests (1,170 Python, 283 Node), the standalone 16-case readiness check,
and GitHub Actions run `40183596018`. The frozen-study change also passed the
separate offline ML workflow. The consolidation must pass both applicable CI
workflows against main before merging.

Review the complete diff against prior main
`cf47600b6294a31d534929b8cc0ad81f0a6259b0`, not just the final documentation commit.
Use a merge commit to preserve the ten existing commit identities. Confirm the
merged tree equals the tested release tree, then close superseded PRs only after
verifying all ten heads are ancestors of main. Retain the historical branches.

Host acceptance is evaluated separately using private reports; those reports are
not published in this release. CI uses synthetic evidence and cannot establish
current host uptime, chain balances, cloud backup success or strategy quality.

## Host rollout: development checkout only

Run as the regular owner of `~/apps/solana-radar-dev`. Fetch main, then check out
the exact merged commit provided in the release message using `git checkout
--detach <MERGED_COMMIT>`. Inspect `git status --short` first and preserve local
edits; do not use a hard reset, clean command or forced checkout.

Do not overlay the repository onto `~/apps/solana-early-alpha-radar`. Do not run
Compose from `scanner/`, reinstall services, rebuild images or move database
volumes. This source rollout needs none of those operations. The existing
`.venv-research-ml` remains in the development checkout and its dependencies are
unchanged. Private rehearsal journals and the installed experiment live outside
the checkout and remain in place.

The previously accepted readiness command may be used for local inspection if
needed. It does not create a new cycle, sign, submit or query current balances.
There is no reason to replay completed execution or preparation commands merely
because main now contains their source.

## Compatible code rollback

The last accepted source head already understands the current two-cycle journals:

```bash
cd ~/apps/solana-radar-dev
git status --short
git fetch origin feature/devnet-readiness-20261025
git checkout --detach b9504ebc422543d4a7b73e619aeb3ebdb9942781
```

This rolls back only source selection. It does not undo transactions or restore
private data. Do not roll execution tooling back to pre-spending-guard main,
remove reservation/history files, clear STOP, replace the frozen model or reset
the experiment directory. A blocked inspection requires investigation with the
existing evidence retained. Production needs no rollback because this release
does not deploy it.

## Preserve forward evidence without an early evaluation

The normal review helper exports only the last 72 hours. A review on October 27
will not by itself preserve all observations since October 22. Existing captures
or verified local quote backups may contain the earlier evidence, but their
presence must not be assumed. Save a capture now; this command uses the existing
bounded, read-only history exporter and does not call the model evaluator. Its
explicit entry window is October 22 00:00 through October 25 00:00 UTC, so a later
run today does not shift the first study day out of the requested window. Actual
retention coverage remains subject to the exporter's reported bounds.

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"

radar_dev="$HOME/apps/solana-radar-dev"
radar_experiment="$HOME/solana-radar-forward-experiment-20261022"

python3 -E -s - "$radar_dev" "$radar_experiment" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1] + '/forward-study')
from experiment import inspect, private_directory
root = Path(sys.argv[2])
inspect(root)
captures = root / 'captures'
if captures.is_symlink():
    raise SystemExit('Preserve and review the symlink capture directory.')
captures.mkdir(mode=0o700, exist_ok=True)
private_directory(captures)
if len(list(captures.glob('capture-*'))) >= 8:
    raise SystemExit('Capture count cap reached. Preserve all captures for review.')
print('Frozen registration verified; no evaluation performed.')
PY

radar_capture="$radar_experiment/captures/capture-$(date -u +%Y%m%dT%H%M%SZ)-$$"
sudo python3 -E -s "$radar_dev/research-dataset/history.py" \
  --hours 72 --end 2026-10-25T00:00:00Z --output-dir "$radar_capture"
printf 'Preserved locally: %s\nNo model evaluation or refitting performed.\n' "$radar_capture"
SH
```

Run collection as one operation at a time. A failed or partial capture must be
preserved and investigated, not silently deleted to satisfy a count limit. The
existing combined review also enforces a 512 MiB decoded-input limit. Nothing
raises that cap or silently narrows the time window. No Backblaze transfer is
needed. Keep raw captures private; the later review produces its own report.

On October 27, run the unchanged helper from the production project directory:

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/forward-study/collect-review.sh
```

It combines the retained captures, removes overlaps under the existing identity
rules and reports coverage gaps. Do not reinstall the experiment. October 27 is
a review checkpoint: October 22–27 spans six UTC dates, while the existing
qualification minimum is seven distinct UTC dates and 200 valid labels per
target/cohort. An insufficient-evidence result is expected if these guards are
not met; it must not be converted into a pass or a new model fit.

## Next decision

Use the frozen review to select the next specific improvement. Keep strategy
quality separate from execution reliability. General portfolio management,
private-journal disaster recovery and mainnet route validation remain future
engineering work; this consolidation does not claim them complete.
