#!/usr/bin/env bash
set -euo pipefail
umask 077
if [[ $# != 0 || ! -d src || ! -d scripts ]]; then
  echo 'Run without arguments from ~/apps/solana-early-alpha-radar.' >&2; exit 1
fi
bundle="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
source="$PWD/radar-dataset-source-$stamp.json.gz"
output="$PWD/radar-research-dataset-$stamp.json.gz"
temp="$(mktemp "$PWD/.research-dataset-XXXXXX")"
trap 'rm -f -- "$temp"' EXIT
sudo python3 -E -s /usr/local/lib/solana-radar-quotes/0.7.0/manage.py export --hours 72 > "$temp"
ln -- "$temp" "$source"
python3 -E -s "$bundle/build.py" --input "$source" --output "$output"
printf 'Keep the source export: %s\n' "$source"
