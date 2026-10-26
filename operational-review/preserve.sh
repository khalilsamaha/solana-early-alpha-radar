#!/usr/bin/env bash
# Explicit capture-only action. Separate from run.sh; never evaluate the study.
set -euo pipefail
umask 077
radar_dev="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
radar_experiment="$HOME/solana-radar-forward-experiment-20261022"
python3 -E -s - "$radar_dev" "$radar_experiment" <<'PY'
import os
from pathlib import Path
import sys
sys.path.insert(0,sys.argv[1]+'/forward-study')
from experiment import inspect, private_directory
root=Path(sys.argv[2])
inspect(root)
captures=root/'captures'
if captures.is_symlink():raise SystemExit('Stop: capture directory is a symlink.')
captures.mkdir(mode=0o700,exist_ok=True)
private_directory(captures)
count=0
with os.scandir(captures) as entries:
    for entry in entries:
        count+=1
        if count>32:raise SystemExit('Directory cap reached. Preserve existing captures.')
if len(list(captures.glob('capture-*')))>=8:raise SystemExit('Capture limit reached. Preserve existing captures.')
print('Frozen registration verified; no evaluation performed.')
PY
radar_capture="$radar_experiment/captures/capture-$(date -u +%Y%m%dT%H%M%SZ)-$$"
sudo python3 -E -s "$radar_dev/research-dataset/history.py" \
  --hours 72 --output-dir "$radar_capture"
printf 'Preserved locally: %s\nNo study evaluation performed. Keep all captures.\n' "$radar_capture"
