#!/usr/bin/env bash
set -euo pipefail
umask 077
if (( $# != 0 )); then echo 'Usage: review.sh' >&2; exit 2; fi
radar_dev="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
radar_python="$radar_dev/.venv-research-ml/bin/python"
radar_study="$HOME/solana-radar-availability-study-20261029"
test -d "$PWD/src" && test -d "$PWD/scripts"
shopt -s nullglob
radar_captures=("$radar_study"/captures/capture-*)
radar_args=()
for radar_capture in "${radar_captures[@]}"; do
  radar_args+=(--capture-dir "$radar_capture")
done
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  "$radar_python" -E -s "$radar_dev/availability-study/confirmation.py" review \
  --directory "$radar_study" "${radar_args[@]}" \
  --output "$PWD/radar-availability-review-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
