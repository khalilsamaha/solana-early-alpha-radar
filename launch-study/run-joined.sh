#!/usr/bin/env bash
set -euo pipefail
umask 077
bundle="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -d src || ! -d scripts ]]; then
  echo 'Run from ~/apps/solana-early-alpha-radar.' >&2
  exit 1
fi
hours=6
if [[ $# -gt 0 ]]; then
  if [[ $# -ne 2 || $1 != --hours || ! $2 =~ ^([1-9]|1[0-9]|2[0-4])$ ]]; then
    echo 'Usage: bash launch-study/run-joined.sh [--hours 1..24]' >&2
    exit 1
  fi
  hours=$2
fi
# Capture first, then export the already-collected observer ledger. One extra
# quote hour protects the start boundary between the two sequential reads.
quote_hours=$((hours + 1))
work_dir="$(mktemp -d "$PWD/.launch-join-XXXXXX")"
trap 'rm -rf -- "$work_dir"' EXIT
output="$PWD/radar-launch-quotes-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
sudo python3 -E -s "$bundle/report.py" --project "$PWD" --hours "$hours" --output "$work_dir/study.json.gz" > "$work_dir/study.log"
sudo python3 -E -s /usr/local/lib/solana-radar-quotes/0.9.0/manage.py export --hours "$quote_hours" > "$work_dir/quotes.json.gz"
python3 -E -s "$bundle/joined_report.py" --study "$work_dir/study.json.gz" --quotes "$work_dir/quotes.json.gz" --output "$output"
