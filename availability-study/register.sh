#!/usr/bin/env bash
set -euo pipefail
umask 077
if (( $# != 2 )); then
  echo 'Usage: register.sh COMPLETED_REVIEW.json.gz ACCEPTED_DIAGNOSTIC.json.gz' >&2
  exit 2
fi
radar_dev="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
radar_python="$radar_dev/.venv-research-ml/bin/python"
radar_original="$HOME/solana-radar-forward-experiment-20261022"
radar_study="$HOME/solana-radar-availability-study-20261029"
test -x "$radar_python"
test -d "$PWD/src" && test -d "$PWD/scripts"
shopt -s nullglob
radar_captures=("$radar_original"/captures/capture-*)
radar_args=()
for radar_capture in "${radar_captures[@]}"; do
  radar_args+=(--capture-dir "$radar_capture")
done
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  "$radar_python" -E -s "$radar_dev/availability-study/confirmation.py" register \
  --directory "$radar_study" --original-directory "$radar_original" \
  "${radar_args[@]}" --review "$1" --diagnostic "$2" \
  --output "$PWD/radar-availability-registration-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
