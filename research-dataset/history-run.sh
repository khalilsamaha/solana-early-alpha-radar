#!/usr/bin/env bash
set -euo pipefail
umask 077
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --hours|--chunk-hours|--end|--archive)
      [[ $# -ge 2 ]] || { echo "Missing value for $1" >&2; exit 1; }
      args+=("$1" "$2"); shift 2 ;;
    --latest-backup) args+=("$1"); shift ;;
    *) echo 'Usage: history-run.sh [--hours 1..72] [--chunk-hours 1..12] [--end ISO] [--latest-backup | --archive PATH]' >&2; exit 1 ;;
  esac
done
if [[ ! -d src || ! -d scripts ]]; then
  echo 'Run from ~/apps/solana-early-alpha-radar.' >&2; exit 1
fi
bundle="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
output="$PWD/radar-history-$(date -u +%Y%m%dT%H%M%SZ)-$$"
stage="$(mktemp -d "$PWD/.radar-history-XXXXXX")"
trap 'rm -rf -- "$stage"' EXIT
sudo python3 -E -s "$bundle/history.py" "${args[@]}" --output-dir "$stage/capture"
python3 -E -s "$bundle/build.py" --history-dir "$stage/capture" --output "$stage/research-dataset.json.gz"
[[ ! -e "$output" ]] || { echo 'Output already exists.' >&2; exit 1; }
mv -T -- "$stage" "$output"
printf '\nUpload this report: %s/research-dataset.json.gz\n' "$output"
printf 'Keep the capture directory: %s/capture\n' "$output"
