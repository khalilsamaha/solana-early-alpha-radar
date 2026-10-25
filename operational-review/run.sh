#!/usr/bin/env bash
set -euo pipefail
umask 077
radar_tools="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
radar_project="$PWD"
radar_experiment="$HOME/solana-radar-forward-experiment-20261022"
test -f "$radar_project/.env"
sudo -v
python3 -E -s "$radar_tools/operational.py" \
  --project "$radar_project" \
  --experiment "$radar_experiment" \
  --output "$radar_project/radar-operational-review-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
