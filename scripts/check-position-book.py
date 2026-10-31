#!/usr/bin/env python3
"""Run one deterministic CI partition; the union contains every position-book module."""
import argparse
import os
from pathlib import Path
import sys
import unittest


def selected(root, shard):
    return sorted(root.glob('test_*.py'))[shard::3]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('shard',type=int,choices=range(3))
    parser.add_argument('--list',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]/'position-book'
    modules=selected(root,args.shard)
    if not modules:raise SystemExit('Empty position-book partition')
    if args.list:
        print('\n'.join(p.name for p in modules));return
    os.chdir(root);sys.path.insert(0,str(root))
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(p.stem) for p in modules)
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__=='__main__':main()
