#!/usr/bin/env python3
"""Explicit bounded public fee/balance reads for caller-supplied unsigned messages."""
import argparse
import os
from pathlib import Path
import time

from run import read_packet, publish
from evidence import collect, review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--allow-public-read', required=True, action='store_true',
                        help='Read the fixed public RPC for the input network; at most five requests')
    args = parser.parse_args()
    if os.path.lexists(args.output):
        raise ValueError('output-exists')
    # Check publication directory before consuming any public reads.
    if not args.output.parent.is_dir() or not os.access(args.output.parent, os.W_OK):
        raise ValueError('output-directory')
    packet = read_packet(args.input)
    capture = collect(packet)
    result = review(packet, capture, now_ms=time.time_ns()//1000000)
    publish(args.output, dict(format='execution-cost-public-review-1', capture=capture, review=result))
    print('State:', result['state'])
    print('Public read requests:', capture['networkRequests'])
    if result['economics'] is not None:
        print('Assumption-based economics:', result['economics']['state'])
    print('No route validation, signing, sending or execution approval.')
    print('Report:', args.output.absolute())
    return 0 if result['state'] in ('fee-and-native-evidence-consistent', 'devnet-fee-evidence-only') else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, TypeError, KeyError, RecursionError):
        raise SystemExit('Evidence review stopped: invalid input or unavailable output. No transaction sent.') from None
