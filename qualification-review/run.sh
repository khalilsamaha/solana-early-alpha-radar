#!/usr/bin/env bash
set -euo pipefail
umask 077
if [[ $# != 0 || ! -d src || ! -d scripts ]]; then
  echo 'Run without arguments from ~/apps/solana-early-alpha-radar.' >&2; exit 1
fi
bundle="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
quote="$PWD/radar-review-source-$stamp.json.gz"
output="$PWD/radar-qualification-review-$stamp.json.gz"
temp="$(mktemp "$PWD/.qualification-review-XXXXXX")"
trap 'rm -f -- "$temp"' EXIT
sudo python3 -E -s /usr/local/lib/solana-radar-quotes/0.7.0/manage.py export --hours 24 > "$temp"
ln -- "$temp" "$quote"
python3 -E -s "$bundle/review.py" --input "$quote" --output "$output"
printf 'Keep the source export for follow-up: %s\n' "$quote"
