#!/usr/bin/env bash
set -euo pipefail
umask 077
radar_dev="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
sudo -v
python3 -E -s "$radar_dev/operational-review/profile-stats.py" \
  --project "$PWD" --projected \
  --output "$PWD/radar-statistics-projected-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
