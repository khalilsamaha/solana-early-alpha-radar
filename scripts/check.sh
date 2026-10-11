#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export PYTHONDONTWRITEBYTECODE=1
python3 scripts/check-source.py
(
  cd scanner
  node --test test/*.test.js
  python3 -m unittest discover -s test -p 'test_*.py'
)
(
  cd quote-observer
  node --test *.test.mjs
  python3 -m unittest discover -p 'test_*.py'
)
(
  cd research-tools
  python3 -m unittest discover -p 'test_*.py'
)
(
  cd quality-tools
  python3 -m unittest discover -p 'test_*.py'
)

(
  cd deployment
  python3 -m unittest discover -p 'test_*.py'
)

(
  cd operations-tools
  python3 -m unittest discover -p 'test_*.py'
)
