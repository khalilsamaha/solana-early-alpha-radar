#!/usr/bin/env bash
set -euo pipefail
umask 077
bundle="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
output="$PWD/radar-launch-audit-$(date -u +%Y%m%dT%H%M%SZ)-$$.json"
tmp="$(mktemp "$PWD/.launch-audit-XXXXXX")"
trap 'rm -f -- "$tmp"' EXIT
sudo python3 -E -s "$bundle/launch_audit.py" --project "$PWD" "$@" > "$tmp"
mv -- "$tmp" "$output"
printf 'Upload: %s\n' "$output"
