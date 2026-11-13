"""Imports and source identity for the isolated combined integration candidate."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
for name in ('r1-session', 'r1-registration', 'r1-data', 'r1-runtime',
             'r1-service', 'r1-container-review', 'r1-preservation'):
    sys.path.append(str(REPO/name))
import session as accepted_session
from capture import CaptureError, canonical, digest, exclusive_file, strict_json
from handoff import path_without_links, read_private
from supervisor import ENVIRONMENT

def raw(row):
    return (canonical(row)+'\n').encode()

def pins():
    result=accepted_session.pins()
    import integrated_common
    result.update(integrated_common.pins())
    for path in sorted([*ROOT.glob('*.py'), *ROOT.glob('*.md'), REPO/'scripts/r1-integration-kali.sh']):
        if path.is_symlink(): raise CaptureError('integration-source-link')
        result[str(path.relative_to(REPO))]=digest(path.read_bytes())
    return dict(sorted(result.items()))
