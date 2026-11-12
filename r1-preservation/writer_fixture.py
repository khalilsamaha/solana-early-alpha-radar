"""Fixed network-disabled writer for clean-close and SIGKILL preservation tests."""
import os
from pathlib import Path
import signal
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'r1-data'))
from supervisor_worker import bootstrap


def run(directory,parent,mode):
    bootstrap(parent)
    from capture import Capture,Limits,canonical
    from measurement import Journal
    from supervisor import ENVIRONMENT
    if dict(os.environ)!=ENVIRONMENT or mode not in ('complete','interrupted','rollback'):
        raise RuntimeError('writer-environment')
    path=Path(directory);mint='1'*31+'2'
    with Journal(path/'session.jsonl') as journal:
        with Capture(path/'capture',Limits(messages=4,seconds=5,sample_modulus=1)) as capture:
            journal.start(capture)
            stamp=journal.stamp()
            capture.receive(canonical({'txType':'create','mint':mint,'signature':'2'*88}).encode())
            journal.selected(capture,stamp)
            intent=journal.intent({'method':'subscribeTokenTrade','keys':[mint]},capture)
            if mode=='rollback':
                # A real uncommitted SQLite transaction leaves its rollback file.
                capture.db.execute('PRAGMA cache_size=1')
                capture.db.execute('BEGIN IMMEDIATE')
                capture.db.execute('UPDATE state SET value=? WHERE id=1',(canonical(capture.state)+' '*8192,))
                if not (path/'capture/ticks.db-journal').stat().st_size:
                    raise RuntimeError('writer-rollback-missing')
            if mode!='complete':
                print('ready',flush=True)
                while True:signal.pause()
            journal.sent(intent)
            for kind in ('buy','sell','migration'):
                capture.receive(canonical({'txType':kind,'mint':mint,'signature':'2'*88}).encode())
            journal.finish('capture-stopped',capture)
    print('ready',flush=True)


if __name__=='__main__':
    try:
        if len(sys.argv)!=4:raise RuntimeError('writer-arguments')
        run(sys.argv[1],int(sys.argv[2]),sys.argv[3])
    except BaseException:sys.exit(1)
