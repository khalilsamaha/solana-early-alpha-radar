"""Fixed synthetic profile probe. No provider, credential or custom-command mode."""
import json
import os
import signal
import socket
import subprocess
import sys
import time
import runtime as r


def main():
    directory,sha,parent,mode=sys.argv[1:];parent=int(parent)
    r.m.check(mode in ('complete','ignore-alarm','dns','process','socket','tainted-output','output-flood'),'runtime-fixture-mode')
    manifest=r.m.inspect(directory,sha)
    row=r.bootstrap(parent,manifest)
    if mode=='ignore-alarm':
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGTERM,signal.SIG_IGN)
        while True:time.sleep(.1)
    blocked=False
    if mode in ('dns','process','socket'):
        try:
            if mode=='dns':socket.getaddrinfo('example.invalid',443)
            elif mode=='socket':socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            else:subprocess.Popen([sys.executable,'-c','pass'])
        except ValueError as exc:
            r.m.check(str(exc)=='runtime-offline-only','runtime-guard-error');blocked=True
        r.m.check(blocked,'runtime-guard-missed')
    if mode=='tainted-output':
        print('not-a-terminal-receipt');return
    if mode=='output-flood':
        while True:os.write(1,b'x'*4096)
    r.m.check(os.getppid()==parent,'runtime-parent-changed')
    print(json.dumps({'schema':1,'kind':'synthetic-runtime-terminal','manifest_sha256':sha,
                      'profile':row,'mode':mode,'guard_blocked':blocked,'source_sha256':r.pins(),
                      'production_modified':False,'provider_connection_opened':False},sort_keys=True,separators=(',',':')))


if __name__=='__main__':
    try:main()
    except BaseException:sys.exit(2)
