#!/usr/bin/env bash
set -euo pipefail
umask 077
radar_dev="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
sudo -v
python3 -E -s "$radar_dev/statistics-lab/run-compact.py" \
  --project "$PWD" \
  --output "$PWD/radar-statistics-compact-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
