#!/usr/bin/env bash
set -euo pipefail
umask 077
if [[ $# != 0 || ! -d src || ! -d scripts ]]; then
  echo 'Run without arguments from ~/apps/solana-early-alpha-radar.' >&2
  exit 1
fi
bundle="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
output="$PWD/radar-source-comparison-$(date -u +%Y%m%dT%H%M%SZ)-$$.json"
temp="$(mktemp "$PWD/.source-comparison-XXXXXX")"
trap 'rm -f -- "$temp"' EXIT
run_status=0
sudo /usr/bin/flock -n /run/lock/solana-radar-source-comparison.lock \
  /usr/bin/node --max-old-space-size=128 "$bundle/collector.mjs" > "$temp" || run_status=$?
python3 - "$temp" <<'PY'
import json, sys
try:
    with open(sys.argv[1]) as handle:
        report = json.load(handle)
    assert report.get('format') == 'source-comparison-1'
    assert report.get('state') != 'collecting'
except Exception:
    raise SystemExit('No complete report was produced; check the error above.')
PY
# A second run cannot overwrite the completed report.
ln -- "$temp" "$output"
printf 'Upload: %s\n' "$output"
exit "$run_status"
