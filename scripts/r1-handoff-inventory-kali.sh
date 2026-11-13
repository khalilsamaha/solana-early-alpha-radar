#!/usr/bin/env bash
# Read-only production metadata; no service control, credentials, provider or RPC.
set -euo pipefail
umask 077
test "$#" -eq 0
source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
review_root="$(dirname -- "$source_root")"
test "$(basename -- "$source_root")" = source
test -z "$(git -C "$source_root" status --porcelain)"
test ! -e "$review_root/results"
cd -- "$source_root"
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
python3 -E -s -B scripts/check-source.py
timeout --signal=TERM --kill-after=5s 45s python3 -E -s -B -W error::ResourceWarning \
  r1-handoff-review/inventory.py --observe-local-container --output-directory "$review_root/results"
printf 'Upload report.json, prerequisites.json and validation.log from: %s/results\n' "$review_root"
