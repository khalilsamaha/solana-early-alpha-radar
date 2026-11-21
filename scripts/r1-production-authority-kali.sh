#!/usr/bin/env bash
set -euo pipefail
umask 077
test "$#" = 1
source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
review="$(dirname -- "$source_root")"
test "$(basename -- "$source_root")" = source
test ! -e "$review/results"
cd "$source_root"
test -z "$(git status --porcelain)"
python3 -E -s -B r1-production-review/authority.py \
  --baseline-root "$HOME" --baseline-sha256 "$1" --output "$review/results"
