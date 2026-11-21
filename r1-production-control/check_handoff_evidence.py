"""Verify a supplied offline archive and external digest; never contact its host."""
import argparse
from pathlib import Path
import handoff_evidence as evidence
c=evidence.c


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',required=True)
    parser.add_argument('--sha256',required=True)
    args=parser.parse_args(argv)
    try:
        path=Path(args.archive);cap=evidence.MAX_TOTAL+evidence.MAX_MANIFEST+131072
        raw=c.read(path,cap);_,assessment=evidence.verify(raw,args.sha256)
        c.check(c.read(path,cap)==raw,'handoff-reader-input-changed')
        result={'schema':1,'status':'verified-historical-offline-evidence','sha256':args.sha256,
                'assessment':assessment,'live_host_observed':False,'activation_authorized':False}
        code=0 if assessment['classification']=='closed-restored-offline-handoff-evidence' else 2
    except Exception:
        # Do not echo untrusted archive contents or host paths in diagnostics.
        result={'schema':1,'status':'invalid-or-unavailable-handoff-evidence',
                'live_host_observed':False,'activation_authorized':False};code=1
    print(c.raw(result).decode(),end='');return code


if __name__=='__main__':raise SystemExit(main())
