#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export PYTHONDONTWRITEBYTECODE=1
case "${1:-all}" in
  all|core|core-base|devnet-pool|position-book-0|position-book-1|position-book-2) radar_check_group="${1:-all}" ;;
  *) echo 'Usage: scripts/check.sh [all|core|core-base|devnet-pool|position-book-0|position-book-1|position-book-2]' >&2; exit 2 ;;
esac
if (( $# > 1 )); then
  echo 'Usage: scripts/check.sh [all|core|core-base|devnet-pool|position-book-0|position-book-1|position-book-2]' >&2
  exit 2
fi
if [[ "$radar_check_group" == position-book-* ]]; then
  python3 scripts/check-position-book.py "${radar_check_group##*-}"
  exit
fi
if [[ "$radar_check_group" == devnet-pool ]]; then
  cd devnet-pool
  python3 -m unittest discover -p 'test_*.py'
  exit
fi
python3 scripts/check-source.py
node --test source-comparison/*.test.mjs
node --test operational-review/*.test.mjs
node --test statistics-lab/*.test.mjs
node --test deployment/*.test.mjs
(cd statistics-lab && python3 -m unittest discover -p 'test_*.py')
(cd operational-review && python3 -m unittest discover -p 'test_*.py')
(cd qualification-review && python3 -m unittest discover -p 'test_*.py')
(cd research-dataset && python3 -m unittest discover -p 'test_*.py')
(cd execution-cost && python3 -m unittest discover -p 'test_*.py')
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
  python3 -m unittest discover -p 'test_capture_review.py'
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

if [[ "$radar_check_group" != core-base ]]; then
  (
    cd position-book
    python3 -m unittest discover -p 'test_*.py'
  )
fi

(
  cd swap-contract
  python3 -m unittest discover -p 'test_*.py'
)

(
  cd swap-state
  python3 -m unittest discover -p 'test_*.py'
)

(
  cd swap-program
  python3 -m unittest discover -p 'test_*.py'
)

(
  cd swap-preflight
  python3 -m unittest discover -p 'test_*.py'
)

(
  cd swap-rehearsal
  python3 -m unittest discover -p 'test_*.py'
)

(
  cd devnet-setup
  python3 -m unittest discover -p 'test_*.py'
)

(
  cd devnet-token-pair
  python3 -m unittest discover -p 'test_*.py'
)

(
  if [[ "$radar_check_group" == all ]]; then
    cd devnet-pool
    python3 -m unittest discover -p 'test_*.py'
  fi
)
