#!/usr/bin/env bash
set -euo pipefail
umask 077
source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
review="$(dirname -- "$source_root")"
test "$(basename -- "$source_root")" = source
test ! -e "$review/results"
python3 -m venv "$review/venv"
"$review/venv/bin/python" -m pip --isolated --disable-pip-version-check install --no-deps --only-binary=:all: --require-hashes -r "$source_root/r1-data/requirements-wire.txt"
cd "$source_root"
timeout --signal=TERM --kill-after=10s 300s "$review/venv/bin/python" -E -s -B -W error::ResourceWarning r1-integration/check_integration.py --output-directory "$review/results"
