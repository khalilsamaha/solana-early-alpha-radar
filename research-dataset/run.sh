#!/usr/bin/env bash
set -euo pipefail
umask 077
hours=24
if [[ $# == 2 && "$1" == --hours && "$2" =~ ^([1-9]|[1-6][0-9]|7[0-2])$ ]]; then
  hours="$2"
elif [[ $# != 0 ]]; then
  echo 'Usage: bash research-dataset/run.sh [--hours 1..72]' >&2; exit 1
fi
if [[ ! -d src || ! -d scripts ]]; then
  echo 'Run from ~/apps/solana-early-alpha-radar.' >&2; exit 1
fi
bundle="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
source="$PWD/radar-dataset-source-$stamp.json.gz"
output="$PWD/radar-research-dataset-$stamp.json.gz"
temp="$(mktemp "$PWD/.research-dataset-XXXXXX")"
trap 'rm -f -- "$temp"' EXIT
printf 'Requested export window: last %s hours (no automatic narrowing).\n' "$hours"
if ! sudo python3 -E -s /usr/local/lib/solana-radar-quotes/0.7.0/manage.py export --hours "$hours" > "$temp"; then
  echo 'No source or dataset report published. If the exporter reported a cap, rerun with an explicitly smaller --hours value, such as 12.' >&2
  exit 1
fi
ln -- "$temp" "$source"
python3 -E -s "$bundle/build.py" --input "$source" --output "$output"
printf 'Keep the source export: %s\n' "$source"
