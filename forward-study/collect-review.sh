#!/usr/bin/env bash
# Read the local quote ledger, preserve the capture, and evaluate immutable models.
set -euo pipefail
umask 077
if (( $# != 0 )); then
  echo 'Usage: collect-review.sh (run from the live project directory)' >&2
  exit 2
fi
radar_project="$PWD"
radar_dev="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
radar_experiment="$HOME/solana-radar-forward-experiment-20261022"
radar_python="$radar_dev/.venv-research-ml/bin/python"
test -d "$radar_project/src" && test -d "$radar_project/scripts"
if [[ ! -x "$radar_python" ]]; then
  echo 'Missing isolated research environment; follow FROZEN-FORWARD-STUDY-UPDATE.md.' >&2
  exit 1
fi
"$radar_python" -E -s - "$radar_dev" "$radar_experiment" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + '/forward-study')
from experiment import inspect
inspect(sys.argv[2])
PY
if [[ -L "$radar_experiment/captures" ]]; then
  echo 'Refusing symlink capture directory.' >&2
  exit 1
fi
mkdir -p -m 700 "$radar_experiment/captures"
shopt -s nullglob
radar_previous=("$radar_experiment"/captures/capture-*)
if (( ${#radar_previous[@]} >= 8 )); then
  echo 'Eight-capture review cap reached. Preserve all evidence; request a review before collecting another batch here.' >&2
  exit 1
fi
radar_stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
radar_capture="$radar_experiment/captures/capture-$radar_stamp"
sudo python3 -E -s "$radar_dev/research-dataset/history.py" \
  --hours 72 --output-dir "$radar_capture"
radar_args=()
for radar_path in "${radar_previous[@]}" "$radar_capture"; do
  radar_args+=(--capture-dir "$radar_path")
done
radar_output="$radar_project/radar-frozen-forward-$radar_stamp.json.gz"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  "$radar_python" -E -s "$radar_dev/forward-study/experiment.py" evaluate \
  --directory "$radar_experiment" "${radar_args[@]}" --output "$radar_output"
printf 'Keep every capture under: %s/captures\n' "$radar_experiment"
