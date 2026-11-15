"""Bounded synthetic owner subprocess: Unix only, or explicit development pipe."""
import ctypes
import json
import os
from pathlib import Path
import resource
import signal
import socket
import struct
import sys


def main():
    registry=Path(sys.argv[1]);parent=int(sys.argv[2]);pipe_fd=int(sys.argv[3]);cleanup=sys.argv[4]
    if cleanup not in ('unsubscribed','upstream-aborted') or os.getppid()!=parent:raise ValueError('parent')
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(1,signal.SIGKILL,0,0,0)!=0 or os.getppid()!=parent:raise ValueError('parent-death')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(30,30))
    resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2));signal.alarm(90)
    native=pipe_fd<0;server=peer=None;output=None;started=False;retired=False;closed=False
    def emit(v):print(json.dumps(v,sort_keys=True,separators=(',',':')),flush=True)
    def close_connection():
        nonlocal closed
        if closed:return
        if peer:peer.shutdown(socket.SHUT_WR);peer.close()
        if output:output.close()
        closed=True
    def send(seq,kind,mint):
        value={'v':1,'seq':seq,'event':{'txType':kind,'mint':'1'*31+mint,'signature':'2'*88,'initialBuy':0}}
        data=(json.dumps(value,separators=(',',':'))+'\n').encode()
        if native:peer.sendall(data)
        else:output.write(data);output.flush()
    try:
        if native:
            server=socket.socket(socket.AF_UNIX);server.settimeout(8)
            server.bind(str(registry/'discovery.sock'));os.chmod(registry/'discovery.sock',0o600);server.listen(1)
        else:output=os.fdopen(pipe_fd,'wb')
        emit({'event':'bound','development':not native,'attempts':0})
        for line in sys.stdin:
            command=line.strip()
            if command=='peer' and not started:
                if native:
                    if peer is not None:raise ValueError('second-peer')
                    peer=server.accept()[0];peer.settimeout(3)
                    pid,uid,gid=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                    if uid!=os.getuid() or gid!=os.getgid():raise ValueError('peer-owner')
                    emit({'event':'peer','pid':pid,'uid':uid,'gid':gid,'development':False})
                else:emit({'event':'peer','development':True})
            elif command=='start' and not started and not retired and (peer or output):
                started=True;send(1,'create','2');send(2,'migration','2')
                emit({'event':'started','synthetic_attempts':1})
            elif command=='retire' and started and not retired:
                retired=True
                if cleanup=='unsubscribed':send(3,'create','3')
                else:close_connection()
                emit({'event':'retired','cleanup':cleanup,'admission_closed':True,'discovery_continues':not closed})
            elif command=='stop' and started and retired:
                close_connection();emit({'event':'stopped','closed':True});return 0
            else:raise ValueError('command-order')
        raise ValueError('parent-eof')
    finally:
        if peer and not closed:peer.close()
        if output and not closed:output.close()
        if server:server.close()

if __name__=='__main__':
    try:sys.exit(main())
    except BaseException as e:
        if isinstance(e,SystemExit):raise
        print('native-owner-stopped-unconfirmed',file=sys.stderr);sys.exit(1)
