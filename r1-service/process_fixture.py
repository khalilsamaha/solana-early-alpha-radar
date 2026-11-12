"""Fixed no-network service stand-in; never runs scanner or provider code."""
import os
from pathlib import Path
import signal
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'r1-data'))

if __name__=='__main__':
    try:
        if len(sys.argv)!=3 or sys.argv[1] not in {'direct','consumer','owner'}:raise RuntimeError()
        from supervisor_worker import bootstrap
        bootstrap(int(sys.argv[2]))
        # This fixture's small stdout protocol contains fixed words only.
        print('ready',flush=True)
        for line in sys.stdin:
            if line=='retire\n' and sys.argv[1]=='owner':print('retired',flush=True)
            elif line=='abort\n' and sys.argv[1]=='owner':break
            else:raise RuntimeError()
    except BaseException:
        sys.exit(1)
