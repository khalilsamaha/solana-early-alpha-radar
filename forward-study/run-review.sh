#!/usr/bin/env bash
set -euo pipefail
umask 077
radar_tools="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$HOME/apps/solana-early-alpha-radar"
test "$#" -eq 1 || { echo 'Usage: bash run-review.sh /path/to/capture'; exit 2; }
python3 -E -s "$radar_tools/readiness_details.py" \
  --history-dir "$1" \
  --registration "$PWD/radar-forward-protocol-registration.json.gz" \
  --output "$PWD/radar-readiness-details-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
