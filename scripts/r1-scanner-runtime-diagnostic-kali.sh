#!/usr/bin/env bash
set -euo pipefail
umask 077
source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
review="$(dirname -- "$source_root")"
test "$(basename -- "$source_root")" = source
test ! -e "$review/results"
cd "$source_root"
python3 -E -s -B -W error::ResourceWarning r1-image/check_runtime.py --output-directory "$review/results" --diagnose-existing-image
