#!/bin/bash
set -euo pipefail
umask 077
bundle="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
hours=12
if [ "$#" -ne 0 ]; then
  if [ "$#" -ne 2 ] || [ "$1" != --hours ] || ! [[ "$2" =~ ^([1-9]|1[0-9]|2[0-4])$ ]]; then
    echo 'Usage: bash run-evidence.sh [--hours 1..24]' >&2; exit 2
  fi
  hours="$2"
fi
stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
quotes="$PWD/radar-auto-quotes-$stamp.json.gz"
output="$PWD/radar-evidence-review-$stamp.json.gz"
tmp="$(mktemp "$PWD/.radar-evidence-XXXXXX")"
trap 'rm -f -- "$tmp"' EXIT
sudo python3 -E -s /usr/local/lib/solana-radar-quotes/0.6.0/manage.py export --hours "$hours" > "$tmp"
ln -- "$tmp" "$quotes"
rm -- "$tmp"
trap - EXIT
printf 'Quote export: %s\n' "$quotes"
sudo python3 -E -s "$bundle/quality_report.py" --project "$PWD" --hours "$hours" --quotes "$quotes" --output "$output"
