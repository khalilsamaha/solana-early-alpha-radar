#!/usr/bin/env bash
set -euo pipefail
umask 077
mode="${1:---live}"
case "$mode" in
  --live) hours=2 ;;
  --backup) hours=24 ;;
  *) echo 'Usage: bash run-now.sh [--live|--backup]' >&2; exit 2 ;;
esac
cd "$HOME/apps/solana-early-alpha-radar"
report_file="$(mktemp "$PWD/radar-research-${mode#--}-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX.json.gz")"
trap 'rm -f -- "$report_file"' ERR
sudo /usr/local/sbin/radar-research "$mode" --hours "$hours" --output "$report_file"
sudo chown "$(id -u):$(id -g)" "$report_file"
chmod 600 "$report_file"
printf '\nUpload this report: %s\n' "$report_file"
