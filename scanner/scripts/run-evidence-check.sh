#!/usr/bin/env bash
set -euo pipefail
umask 077
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$HOME/apps/solana-early-alpha-radar"
report_file="$(mktemp "$PWD/radar-evidence-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX.json.gz")"
trap 'rm -f -- "$report_file"' ERR
sudo python3 "$script_dir/evidence-check.py" --output "$report_file"
sudo chown "$(id -u):$(id -g)" "$report_file"
chmod 600 "$report_file"
printf 'Report saved: %s\nUpload this .json.gz file for analysis.\n' "$report_file"
