#!/usr/bin/env bash
set -euo pipefail
umask 077
source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
review="$(dirname -- "$source_root")"
test "$(basename -- "$source_root")" = source
test ! -e "$review/results"
cd "$source_root"
test -z "$(git status --porcelain)"
python3 -E -s -B -W error::ResourceWarning r1-production-review/check_intake.py \
  --observe-local-container --output-directory "$review/results"
