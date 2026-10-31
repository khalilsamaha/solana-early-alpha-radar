#!/usr/bin/env python3
"""Run one deterministic CI partition; the union contains every position-book module."""
import argparse
from pathlib import Path
import sys
import subprocess


def selected(root, shard):
    files=sorted(root.glob('test_*.py'))
    # This module alone takes about 8.5 minutes; do not add other work to its job.
    dedicated='test_exit_submission.py'
    if shard==6:return [p for p in files if p.name==dedicated]
    return [p for p in files[shard::6] if p.name!=dedicated]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('shard',type=int,choices=range(7))
    parser.add_argument('--list',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]/'position-book'
    modules=selected(root,args.shard)
    if not modules:raise SystemExit('Empty position-book partition')
    if args.list:
        print('\n'.join(p.name for p in modules));return
    failed=[]
    for module in modules:
        print(f'Position-book partition {args.shard}: {module.name}',flush=True)
        # Match local module checks; isolate sys.path and test patches per module.
        result=subprocess.run([sys.executable,'-m','unittest','discover','-v','-s',str(root),'-p',module.name],cwd=root)
        if result.returncode:failed.append(module.name)
    if failed:print('Failed modules: '+', '.join(failed),file=sys.stderr,flush=True)
    raise SystemExit(1 if failed else 0)


if __name__=='__main__':main()
