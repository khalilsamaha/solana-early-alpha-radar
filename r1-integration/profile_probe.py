"""Fixed offline profile fault probe; no credential/provider/command interface."""
import common as c
import os
import signal
import sys
import profile


def main():
    if len(sys.argv)!=3 or sys.argv[2] not in ('alarm','guards'):return 1
    profile.bootstrap(int(sys.argv[1]),profile.make(1,setup_seconds=1,shutdown_seconds=1))
    if sys.argv[2]=='alarm':
        print('armed',flush=True)
        while True:signal.pause()
    import socket
    import subprocess
    blocked=[]
    for name,fn in (('internet',lambda:socket.socket(socket.AF_INET)),
                    ('dns',lambda:socket.getaddrinfo('invalid.invalid',443)),
                    ('child',lambda:subprocess.Popen(['/bin/true']))):
        try:fn()
        except c.CaptureError:blocked.append(name)
    print(c.canonical({'blocked':blocked}),flush=True)
    return 0 if blocked==['internet','dns','child'] else 1

if __name__=='__main__':sys.exit(main())
