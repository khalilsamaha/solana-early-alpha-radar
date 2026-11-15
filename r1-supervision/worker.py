"""Fixed synthetic profile probe. No provider, credential or custom-command mode."""
import json
import os
import signal
import socket
import subprocess
import sys
import time
import runtime as r
import capture_session as session


def main():
    directory,sha,parent,mode,*extra=sys.argv[1:];parent=int(parent)
    r.m.check(len(extra)<=1,'runtime-fixture-arguments')
    pipe_fd=int(extra[0]) if extra else -1
    r.m.check(mode in {'complete','ignore-alarm','dns','process','socket','tainted-output','output-flood'}|session.MODES,'runtime-fixture-mode')
    manifest=r.m.inspect(directory,sha)
    native_development=False
    if mode in session.NATIVE_MODES:
        import native_scanner
        claim,_=native_scanner.read(manifest['config']['registry_path'],'supervision-claim.json')
        native_development=claim['native_development']
        r.m.check(type(native_development) is bool,'native-development-flag')
    row=r.bootstrap(parent,manifest)
    if mode not in session.MODES:r.m.check(pipe_fd==-1,'unexpected-scanner-pipe')
    evidence=session.run(manifest,mode,pipe_fd,native_development) if mode in session.MODES else None
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
    terminal={'schema':1,'kind':'synthetic-runtime-terminal','manifest_sha256':sha,
                      'profile':row,'mode':mode,'guard_blocked':blocked,'source_sha256':r.pins(),
                      'production_modified':False,'provider_connection_opened':False}
    if evidence is not None:terminal['session_evidence']=evidence
    print(json.dumps(terminal,sort_keys=True,separators=(',',':')))


if __name__=='__main__':
    try:main()
    except BaseException:sys.exit(2)
