#!/usr/bin/env bash
# Explicit local ledger capture only; this helper never evaluates the study.
set -euo pipefail
umask 077
if (( $# != 0 )); then echo 'Usage: preserve.sh' >&2; exit 2; fi
radar_dev="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
radar_python="$radar_dev/.venv-research-ml/bin/python"
radar_study="$HOME/solana-radar-availability-study-20261029"
test -d "$PWD/src" && test -d "$PWD/scripts"
radar_end="$("$radar_python" -E -s - "$radar_dev" "$radar_study" <<'PY'
import datetime as dt
from pathlib import Path
import sys
sys.path.insert(0,sys.argv[1]+'/availability-study')
import confirmation as study
now=study.frozen.clock()
_,r=study.load(sys.argv[2],now)
if now<r['startAt']:raise SystemExit('Collection window has not started.')
p=Path(sys.argv[2])/'captures'
if p.is_symlink():raise SystemExit('Unsafe capture directory.')
p.mkdir(mode=0o700,exist_ok=True)
study.frozen.private_directory(p)
if len(list(p.glob('capture-*')))>=8:raise SystemExit('Eight-capture cap reached; preserve everything.')
end=min(now,r['reviewNotBeforeAt'])
print(dt.datetime.fromtimestamp(end/1000,dt.timezone.utc).isoformat())
PY
)"
radar_capture="$radar_study/captures/capture-$(date -u +%Y%m%dT%H%M%SZ)-$$"
sudo python3 -E -s "$radar_dev/research-dataset/history.py" \
  --hours 72 --end "$radar_end" --output-dir "$radar_capture"
printf 'Preserved without evaluation: %s\n' "$radar_capture"
