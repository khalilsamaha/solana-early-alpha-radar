"""Manifest-bound finite resource profile. Network remains disabled in this candidate."""
import ctypes
import os
from pathlib import Path
import resource
import signal
import socket
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'r1-deployment'))
import manifest as m
import preparation as preparation


def pins():
    return {**preparation.pins(),**{str(p.relative_to(ROOT.parent)):m.digest(p.read_bytes())
            for p in sorted(ROOT.iterdir()) if p.suffix in ('.py','.md')}}


def profile(manifest):
    m.check(m.raw(manifest)==m.raw(m.build(manifest['config'],manifest['policy'])),'runtime-manifest')
    policy=manifest['policy']
    keys=('service_seconds','setup_seconds','shutdown_seconds','memory_bytes','cpu_seconds','open_files')
    m.check(all(policy[k] is not None for k in keys) and manifest['capacity'] is not None,'runtime-policy-missing')
    m.check(policy['memory_bytes']>=64*1024**2 and 16<=policy['open_files']<=4096,'runtime-resource-range')
    row={k:policy[k] for k in keys}
    row.update(core_bytes=0,file_bytes=manifest['capacity']['envelope_max_bytes'],
               wall_seconds=sum(policy[k] for k in ('service_seconds','setup_seconds','shutdown_seconds')),
               network_enabled=False,live_profile_accepted=False)
    for value in (row['memory_bytes'],row['cpu_seconds'],row['file_bytes']):
        m.check(value<2**63-1,'runtime-platform-range')
    return row


def bootstrap(parent,manifest):
    row=profile(manifest)
    m.check(sys.platform=='linux' and type(parent) is int and parent>1,'runtime-platform')
    m.check(ctypes.CDLL(None,use_errno=True).prctl(1,signal.SIGKILL,0,0,0)==0 and os.getppid()==parent,'runtime-parent')
    os.umask(0o077)
    for kind,name in ((resource.RLIMIT_CORE,'core_bytes'),(resource.RLIMIT_AS,'memory_bytes'),
                      (resource.RLIMIT_CPU,'cpu_seconds'),(resource.RLIMIT_FSIZE,'file_bytes'),
                      (resource.RLIMIT_NOFILE,'open_files')):
        resource.setrlimit(kind,(row[name],row[name]))
        m.check(resource.getrlimit(kind)==(row[name],row[name]),'runtime-limit-not-applied')
    signal.signal(signal.SIGALRM,signal.SIG_DFL);signal.setitimer(signal.ITIMER_REAL,row['wall_seconds'])
    def guard(event,args):
        if (event in {'subprocess.Popen','os.fork','os.forkpty','os.posix_spawn','os.exec',
                      'socket.getaddrinfo','socket.gethostbyname','socket.gethostbyaddr','socket.getnameinfo'}
                or event=='socket.__new__' and args[1] in (socket.AF_INET,socket.AF_INET6)
                or event in {'socket.connect','socket.sendto'} and args[0].family in (socket.AF_INET,socket.AF_INET6)):
            raise ValueError('runtime-offline-only')
    sys.addaudithook(guard)
    return row
