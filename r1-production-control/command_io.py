"""Bounded CLI stdout/stderr separation; retain only constant diagnostics."""
import os
import selectors
import signal
import subprocess
import time


def bounded(command, *, seconds=15, cap=262144, env=None, events=None):
    if type(seconds) not in (int, float) or not 0 < seconds <= 65 or type(cap) is not int or not 1 <= cap <= 262144:
        raise ValueError('command-bounds')
    event={'status':'started','stderr_present':False}
    if events is not None:
        if len(events) >= 256: raise ValueError('command-ledger-limit')
        events.append(event)
    process=None; complete=False
    buffers={'stdout':bytearray(),'stderr':bytearray()}
    deadline=time.monotonic()+seconds
    try:
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                 env=env if env is not None else {'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},
                                 start_new_session=True)
        with selectors.DefaultSelector() as selector:
            for stream,name in ((process.stdout,'stdout'),(process.stderr,'stderr')):
                os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,name)
            while selector.get_map():
                left=deadline-time.monotonic()
                if left<=0:raise ValueError('command-timeout')
                ready=selector.select(left)
                if not ready:raise ValueError('command-timeout')
                for key,_ in ready:
                    value=os.read(key.fileobj.fileno(),4096)
                    if not value:selector.unregister(key.fileobj);continue
                    buffers[key.data].extend(value)
                    if key.data=='stderr':event['stderr_present']=True
                    if len(buffers[key.data]) > (cap if key.data=='stdout' else 4096):
                        raise ValueError('command-output-limit' if key.data=='stdout' else 'command-diagnostic-limit')
        try:process.wait(timeout=max(.001,deadline-time.monotonic()))
        except subprocess.TimeoutExpired:raise ValueError('command-timeout') from None
        if process.returncode:raise ValueError('command-failed')
        complete=True;event['status']='completed'
        return bytes(buffers['stdout'])
    except BaseException:
        event['status']='unavailable'
        raise
    finally:
        if process is not None:
            if not complete:
                # Kill the whole client group even if its leader exited while a
                # child still held a pipe. This does not cancel a Docker operation.
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            process.wait(timeout=2)
            process.stdout.close();process.stderr.close()
