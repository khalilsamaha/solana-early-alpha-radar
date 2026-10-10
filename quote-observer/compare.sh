#!/bin/bash
set -euo pipefail
umask 077
if [ "$#" -ne 2 ]; then
  echo 'Usage: bash compare.sh QUOTE_REPORT.json.gz RESEARCH_REPORT.json.gz' >&2
  exit 2
fi
bundle="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
output="$PWD/radar-clock-comparison-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
python3 -E -s "$bundle/evidence_audit.py" --quotes "$1" --research "$2" --out "$output"
printf 'Upload: %s\n' "$output"
