#!/usr/bin/env bash
set -euo pipefail
umask 077
tool_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -d src || ! -d scripts ]]; then
  echo 'Run from ~/apps/solana-early-alpha-radar.' >&2
  exit 1
fi
if [[ $# -gt 0 && ( $# -ne 2 || $1 != --hours || ! $2 =~ ^([1-9]|1[0-9]|2[0-4])$ ) ]]; then
  echo 'Usage: bash launch-study/run-report.sh [--hours 1..24]' >&2
  exit 1
fi
output="$PWD/radar-launch-study-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
sudo python3 -E -s "$tool_dir/report.py" --project "$PWD" --output "$output" "$@"
