"""Finite candidate profiles. Duration support is not live approval or soak evidence."""
import ctypes
import os
import resource
import signal
import socket
import sys
import common


def make(duration_seconds, *, setup_seconds=15, shutdown_seconds=10):
    if (type(duration_seconds) is not int or not 1<=duration_seconds<=172800
            or type(setup_seconds) is not int or not 1<=setup_seconds<=30
            or type(shutdown_seconds) is not int or not 1<=shutdown_seconds<=30):
        raise common.CaptureError('profile-duration')
    return {'schema_version':1,'duration_seconds':duration_seconds,
            'setup_seconds':setup_seconds,'shutdown_seconds':shutdown_seconds,
            'wall_seconds':duration_seconds+setup_seconds+shutdown_seconds,
            'cpu_seconds':min(duration_seconds+30,3600),
            'address_space_bytes':256*1024**2,'file_bytes':96*1024**2,
            'open_files':32,'core_bytes':0,'live_profile_approved':False}


def validate(row):
    if not isinstance(row,dict): raise common.CaptureError('profile-shape')
    expected=make(row.get('duration_seconds'),setup_seconds=row.get('setup_seconds'),
                  shutdown_seconds=row.get('shutdown_seconds'))
    if common.raw(row)!=common.raw(expected): raise common.CaptureError('profile-binding')
    return row


def bootstrap(parent,row):
    validate(row)
    if (sys.platform!='linux' or type(parent) is not int or parent<=1
            or ctypes.CDLL(None,use_errno=True).prctl(1,signal.SIGKILL,0,0,0)!=0
            or os.getppid()!=parent): raise common.CaptureError('profile-parent')
    os.umask(0o077)
    for key,name in ((resource.RLIMIT_CORE,'core_bytes'),(resource.RLIMIT_AS,'address_space_bytes'),
                     (resource.RLIMIT_CPU,'cpu_seconds'),(resource.RLIMIT_FSIZE,'file_bytes'),
                     (resource.RLIMIT_NOFILE,'open_files')):
        value=row[name];resource.setrlimit(key,(value,value))
        if resource.getrlimit(key)!=(value,value): raise common.CaptureError('profile-resource')
    signal.signal(signal.SIGALRM,signal.SIG_DFL)
    signal.setitimer(signal.ITIMER_REAL,row['wall_seconds'])
    def guard(event,args):
        if (event in {'subprocess.Popen','os.fork','os.forkpty','os.posix_spawn','os.exec',
                     'socket.getaddrinfo','socket.gethostbyname','socket.gethostbyaddr','socket.getnameinfo'}
                or event=='socket.__new__' and args[1] in (socket.AF_INET,socket.AF_INET6)
                or event in {'socket.connect','socket.sendto'} and args[0].family in (socket.AF_INET,socket.AF_INET6)):
            raise common.CaptureError('integration-offline-only')
    sys.addaudithook(guard)
