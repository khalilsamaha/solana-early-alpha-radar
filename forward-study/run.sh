#!/usr/bin/env bash
set -euo pipefail
umask 077
bundle="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ $# != 1 || ! -f "$1" ]]; then
  echo 'Usage: bash forward-study/run.sh /absolute/path/to/radar-dataset-source-....json.gz' >&2
  exit 1
fi
source_path="$(realpath -- "$1")"
registration="$PWD/radar-forward-protocol-registration.json.gz"
if [[ ! -e "$registration" ]]; then
  python3 -E -s "$bundle/audit.py" register --output "$registration"
fi
python3 -E -s "$bundle/audit.py" audit --source "$source_path" \
  --registration "$registration" \
  --output "$PWD/radar-forward-readiness-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
