#!/bin/bash
set -euo pipefail
umask 077
bundle="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
output="$PWD/radar-research-quality-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
args=(--project "$PWD" --output "$output")
if [ "$#" -gt 1 ]; then echo 'Usage: bash run-report.sh [QUOTE_REPORT.json.gz]' >&2; exit 2; fi
if [ "$#" -eq 1 ]; then args+=(--quotes "$(realpath -- "$1")"); fi
sudo python3 -E -s "$bundle/quality_report.py" "${args[@]}"
