#!/usr/bin/env bash
# Run from a fresh isolated checkout. No production checkout/service is changed.
set -euo pipefail
umask 077
if [ "$#" -ne 0 ]; then
  printf 'This checker accepts no provider, credential or production arguments.\n' >&2
  exit 2
fi
source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
review_root="$(dirname -- "$source_root")"
test "$(basename -- "$source_root")" = 'source'
test -z "$(git -C "$source_root" status --porcelain)"
test ! -e "$review_root/venv"
test ! -e "$review_root/results"
cd -- "$source_root"
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
python3 --version
node --version
python3 -m venv "$review_root/venv"
"$review_root/venv/bin/python" -m pip --isolated --disable-pip-version-check install \
  --no-deps --only-binary=:all: --require-hashes -r r1-data/requirements-wire.txt
"$review_root/venv/bin/python" -E -s -B scripts/check-source.py
timeout --signal=TERM --kill-after=10s 180s \
  "$review_root/venv/bin/python" -E -s -B -W error::ResourceWarning \
  r1-session/check_session.py --output-directory "$review_root/results"
printf 'Upload: %s/results/acceptance.zip\n' "$review_root"
