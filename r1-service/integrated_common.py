"""Fixed source/resource contract for the synthetic integrated service rehearsal."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
for folder in ('r1-data', 'r1-runtime', 'r1-container-review'):
    sys.path.append(str(REPO / folder))
from capture import digest
from supervisor import ENVIRONMENT
RESOURCES = {'alarm_seconds':45, 'cpu_seconds':10, 'address_space_bytes':256*1024**2,
             'file_bytes':44*1024**2, 'open_files':32, 'core_bytes':0}


def pins():
    import boundary
    import check_container
    result = {**boundary.pins(), **check_container.pins()}
    for pattern in ('*.py', '*.mjs', '*.md'):
        for path in ROOT.glob(pattern):
            if path.is_symlink(): raise RuntimeError('service-source-link')
            result[str(path.relative_to(REPO))] = digest(path.read_bytes())
    return dict(sorted(result.items()))
