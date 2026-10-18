#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export PYTHONDONTWRITEBYTECODE=1
python3 scripts/check-source.py
node --test source-comparison/*.test.mjs
(cd qualification-review && python3 -m unittest discover -p 'test_*.py')
(cd research-dataset && python3 -m unittest discover -p 'test_*.py')
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

(
  cd launch-study
  python3 -m unittest discover -p 'test_*.py'
)

(
  cd forward-study
  python3 -m unittest discover -p 'test_audit.py'
  python3 -m unittest discover -p 'test_readiness_details.py'
)
(
  cd execution-lab
  python3 -m unittest discover -p 'test_*.py'
)

(
  cd chain-reader
  python3 -m unittest discover -p 'test_*.py'
)

(
  cd intent-lab
  python3 -m unittest discover -p 'test_*.py'
)

(
  cd intent-journal
  python3 -m unittest discover -p 'test_*.py'
)

(
  cd recorded-chain
  python3 -m unittest discover -p 'test_*.py'
)

(
  cd devnet-rehearsal
  python3 -m unittest discover -p 'test_*.py'
)

(
  cd token-reconciliation
  python3 -m unittest discover -p 'test_*.py'
)
