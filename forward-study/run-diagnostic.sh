#!/usr/bin/env bash
# Offline replay of the completed study; no collection, refit or runtime change.
set -euo pipefail
umask 077
if (( $# != 1 )); then
  echo 'Usage: run-diagnostic.sh /absolute/path/to/review.json.gz' >&2
  exit 2
fi
radar_dev="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
radar_python="$radar_dev/.venv-research-ml/bin/python"
radar_experiment="$HOME/solana-radar-forward-experiment-20261022"
test -x "$radar_python"
test -f "$1"
test -d "$PWD/src" && test -d "$PWD/scripts"
shopt -s nullglob
radar_captures=("$radar_experiment"/captures/capture-*)
if (( ${#radar_captures[@]} < 1 || ${#radar_captures[@]} > 8 )); then
  echo 'Expected 1..8 preserved capture directories; preserve all evidence.' >&2
  exit 1
fi
radar_args=()
for radar_capture in "${radar_captures[@]}"; do
  radar_args+=(--capture-dir "$radar_capture")
done
radar_output="$PWD/radar-frozen-diagnostic-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  "$radar_python" -E -s "$radar_dev/forward-study/failure_audit.py" \
  --directory "$radar_experiment" "${radar_args[@]}" \
  --review "$1" --output "$radar_output"
