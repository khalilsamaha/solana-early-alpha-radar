#!/usr/bin/env bash
set -euo pipefail
umask 077
source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
review="$(dirname -- "$source_root")"
test "$(basename -- "$source_root")" = source
test ! -e "$review/results"
cd "$source_root"
test -z "$(git status --porcelain)"
# One read-only observation; no repeated rehearsal or tests against production.
# HOME is an explicitly proposed storage filesystem, not an approved capture path.
python3 -E -s -B r1-production-review/readiness.py --storage-root "$HOME" --output "$review/results"
