"""Synthetic lifecycle plus real killed capture writer; not a production rollout."""
import os
from pathlib import Path
import signal
import subprocess
import sys

import preserve
from capture import CaptureError
from supervisor import ENVIRONMENT,kill_group
from integrated_backend import line,reap
from offline_backend import Backend
import lifecycle


def make(root,mode,contract_sha,source_digest):
    root.mkdir(mode=0o700)
    registry=root/'registry';registry.mkdir(mode=0o700)
    journal=root/'lifecycle';journal.mkdir(mode=0o700)
    data=root/'data';data.mkdir(mode=0o700)
    backend=process=None;interrupted=False
    try:
        with lifecycle.Lifecycle(registry,journal,contract_sha,source_digest) as coordinator:
            backend=Backend()
            class Adapter:
                def perform(self,action,op,known):
                    if action=='retire_research' and mode!='complete':raise CaptureError('synthetic-writer-killed')
                    return backend.perform(action,op,known)
            for action in lifecycle.ACTIONS:
                if action=='retire_research':
                    process=subprocess.Popen([sys.executable,'-E','-s','-B','-W','error::ResourceWarning',
                        str(preserve.ROOT/'writer_fixture.py'),str(data),str(os.getpid()),mode],
                        env=ENVIRONMENT,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,close_fds=True,start_new_session=True,bufsize=0)
                    if line(process)!=b'ready\n':raise CaptureError('preservation-writer-start')
                    if mode!='complete':kill_group(process,signal.SIGKILL)
                    process.wait(timeout=2)
                    if process.returncode!=(0 if mode=='complete' else -signal.SIGKILL):
                        raise CaptureError('preservation-writer-exit')
                try:coordinator.step(action,Adapter())
                except CaptureError:
                    if mode=='complete' or action!='retire_research':raise
                    interrupted=True;break
    finally:
        reap(process)
        if backend:backend.close()
    if interrupted!=(mode!='complete'):raise CaptureError('preservation-interruption-expectation')
    return {'mode':mode,'writer_reaped':process.returncode is not None,'writer_exit_code':process.returncode,
            'writer_killed':mode!='complete','native_fixture_cleanup':backend.receipt(),
            'lifecycle_state':lifecycle.inspect(registry,journal),
            'service_handoff_simulated':True,'provider_connection_opened':False}


def save(root,contract_path,sha,output):
    return preserve.preserve(root/'data/capture',root/'data/session.jsonl',root/'registry',
                             root/'lifecycle',contract_path,sha,output)
