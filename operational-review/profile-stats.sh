#!/usr/bin/env bash
set -euo pipefail
umask 077
radar_tools="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
sudo -v
python3 -E -s "$radar_tools/profile-stats.py" \
  --project "$PWD" \
  --output "$PWD/radar-statistics-profile-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
