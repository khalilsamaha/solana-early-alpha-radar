"""Bounded offline diagnostics, never an execution clock or authorization."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import math
import time

VERSION='exit-phase-profile-1'
STAGES=frozenset(('replacement-attempt','collection','rpc-open','source-replay',
    'journal-open','eligibility-replay','lifecycle-replay','evidence-review',
    'provenance-review','replacement-persist','replacement-write','transaction-enter',
    'transaction-commit','transaction-rollback','signing-handoff','signer-backend',
    'transport-submit','freshness-guard'))
MAX_SPANS=1024
_current=ContextVar('offline_exit_profile',default=None)

class Profile:
    def __init__(self,*,clock=lambda:time.time_ns()//1000000,monotonic=time.monotonic):
        self.clock=clock;self.monotonic=monotonic;self.rows=[];self.stack=[]
        self.last=None;self.errors=set();self.deadline=None;self.used=False
    def sample(self):
        try:
            wall=self.clock();tick=self.monotonic()
            valid=(type(wall) is int and 0<wall<2**53 and type(tick) in (int,float)
                and math.isfinite(tick) and tick>=0 and
                (self.last is None or wall>=self.last[0] and tick>=self.last[1]))
        except Exception:valid=False
        if not valid:self.errors.add('diagnostic-clock-invalid');return None
        self.last=(wall,tick);return self.last
    def pin(self,value):
        if type(value) is not int or not 0<value<2**53 or self.deadline not in (None,value):
            self.errors.add('diagnostic-deadline-invalid');return
        self.deadline=value
    def report(self):
        rows=deepcopy(self.rows)
        for i,row in enumerate(rows):
            for source,target in (('startedAtMs','remainingAtStartMs'),('finishedAtMs','remainingAtEndMs')):
                row[target]=None if self.deadline is None or row[source] is None else self.deadline-row[source]
            children=[x for x in rows if x['parentIndex']==i]
            row['exclusiveMs']=None if row['elapsedMs'] is None or any(x['elapsedMs'] is None for x in children) else round(max(0,row['elapsedMs']-sum(x['elapsedMs'] for x in children)),3)
        groups={}
        for row in rows:
            g=groups.setdefault(row['stage'],dict(count=0,incomplete=0,inclusiveMs=0.0,exclusiveMs=0.0))
            g['count']+=1;g['incomplete']+=not row['completed']
            for field,source in (('inclusiveMs','elapsedMs'),('exclusiveMs','exclusiveMs')):
                g[field]=None if g[field] is None or row[source] is None else round(g[field]+row[source],3)
        return dict(format=VERSION,valid=not self.errors,diagnosticCodes=sorted(self.errors),stageTotals=groups,
            originalDeadlineMs=self.deadline,spans=rows,maximumSpans=MAX_SPANS,
            diagnosticOnly=True,extendsDeadline=False,authorizesExecution=False,
            basis='Inclusive spans overlap; exclusive time subtracts direct recorded children. RPC open excludes later body reads. Gaps and wrapper overhead remain unattributed.')

@contextmanager
def capture(profile):
    if type(profile) is not Profile or profile.used or _current.get() is not None:raise ValueError('profile-scope')
    profile.used=True;token=_current.set(profile)
    try:yield profile
    finally:_current.reset(token)

@contextmanager
def measure(stage):
    p=_current.get()
    if p is None:yield;return
    if type(stage) is not str or stage not in STAGES or len(p.rows)>=MAX_SPANS:
        p.errors.add('diagnostic-span-invalid' if type(stage) is not str or stage not in STAGES else 'diagnostic-span-cap')
        yield;return
    start=p.sample();index=len(p.rows)
    row=dict(stage=stage,parentIndex=p.stack[-1] if p.stack else None,
        startedAtMs=None if start is None else start[0],finishedAtMs=None,elapsedMs=None,completed=False)
    p.rows.append(row);p.stack.append(index);complete=False
    try:yield;complete=True
    finally:
        p.stack.pop();end=p.sample()
        if end is not None:row['finishedAtMs']=end[0]
        if start is not None and end is not None:
            elapsed=(end[1]-start[1])*1000
            if math.isfinite(elapsed) and elapsed>=0:row.update(elapsedMs=round(elapsed,3),completed=complete)
            else:p.errors.add('diagnostic-clock-invalid')
