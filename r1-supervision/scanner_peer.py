"""Owned fixed Node scanner-adapter fixture over a pipe; no Docker/live mode."""
import os
from pathlib import Path
import shutil
import subprocess
import time
import runtime as r
import capture_session as session
from adapters import line
m=r.m


def expected(mode):
    normal=session.kind(mode)=='session-normal'
    return {'tokens':3 if normal else 2,'creations':2 if normal else 1,'discovery_gaps':1,
            'sources':['pumpportal:create','pumpportal:migration']+(['pumpportal:create'] if normal else []),
            'upstream_connections_opened':0}


class Scanner:
    def __init__(self):
        self.read_fd,self.write_fd=os.pipe();self.process=None;self.result=None

    def start(self,deadline,setup_seconds):
        node=shutil.which('node');m.check(node is not None,'scanner-node-unavailable')
        command=[node,str(r.ROOT.parent/'r1-data/shared_scanner_fixture.mjs'),'pipe']
        self.process=subprocess.Popen(command,stdin=self.read_fd,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            env=session.c.ENVIRONMENT,close_fds=True,start_new_session=True,bufsize=0)
        os.close(self.read_fd);self.read_fd=None
        m.check(line(self.process,min(setup_seconds,max(.001,deadline-time.monotonic())))==b'ready\n','scanner-ready')

    def writer_passed(self):
        os.close(self.write_fd);self.write_fd=None

    def finish(self,deadline,mode,collect):
        raw,outcome=collect(self.process,max(.001,deadline-time.monotonic()))
        m.check(outcome=='returned' and raw is not None,'scanner-terminal-missing')
        candidate=m.parse(raw)
        m.check(m.raw(candidate)==m.raw(expected(mode)),'scanner-terminal-binding')
        self.result=candidate

    def close(self,reap):
        for name in ('read_fd','write_fd'):
            fd=getattr(self,name)
            if fd is not None:os.close(fd);setattr(self,name,None)
        if self.process is not None:
            try:reap(self.process)
            finally:self.process.stdout.close()

    def snapshot(self):
        return {'kind':'owned-node-scanner-pipe-fixture','started':int(self.process is not None),
                'reaped':self.process is not None and self.process.returncode is not None,
                'returncode':None if self.process is None else self.process.returncode,
                'result':self.result,'transport':'pipe','image_verified':False,
                'manifest_kernel_limits_applied':False,'activation_authorized':False}


def validate(row,mode,*,complete):
    keys={'kind','started','reaped','returncode','result','transport','image_verified',
          'manifest_kernel_limits_applied','activation_authorized'}
    m.check(type(row) is dict and set(row)==keys and row['kind']=='owned-node-scanner-pipe-fixture'
            and row['transport']=='pipe','scanner-receipt-format')
    for k in ('image_verified','manifest_kernel_limits_applied','activation_authorized'):
        m.check(row[k] is False,'scanner-receipt-authority')
    m.check(type(row['started']) is int and row['started'] in (0,1),'scanner-start-count')
    if row['started']:
        m.check(row['reaped'] is True and type(row['returncode']) is int,'scanner-reaping')
    else:m.check(row['reaped'] is False and row['returncode'] is None and row['result'] is None,'scanner-not-started')
    if row['result'] is not None:
        m.check(row['started']==1 and row['returncode']==0 and m.raw(row['result'])==m.raw(expected(mode)),'scanner-result')
    if complete:m.check(row['result'] is not None,'scanner-completion-required')
