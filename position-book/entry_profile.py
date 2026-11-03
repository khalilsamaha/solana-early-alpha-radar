"""Opt-in, bounded diagnostic spans. Never an authority for expiry or execution."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import math
import time

VERSION = 'entry-phase-profile-1'
STAGES = frozenset(('entry-collection', 'admission-open', 'source-before-admission',
    'reserve-admission', 'arm-signing-handoff', 'source-after-admission',
    'commit-signing-boundary', 'validate-signing-request', 'signer-backend',
    'record-signer-ack', 'stage-accounting-handoff', 'sender-open',
    'sender-validation', 'sender-source-replay', 'sender-preflight',
    'commit-send-boundary', 'send-request', 'record-send-ack', 'sender-projection'))
MAX_SPANS = 32
_current = ContextVar('radar_entry_profile', default=None)


class Profile:
    def __init__(self, *, clock=lambda:time.time_ns()//1_000_000, monotonic=time.monotonic):
        self.clock = clock; self.monotonic = monotonic
        self.rows = []; self.errors = set(); self.last = None; self.stack = []
        self.deadline = None; self.send_guard = None; self.used = False

    def sample(self):
        # Diagnostics must not hide an already committed boundary or lost send.
        # Broken diagnostic clocks invalidate the profile, not rewrite execution.
        try:
            wall = self.clock(); tick = self.monotonic()
            valid = (type(wall) is int and 0 < wall < 2**53 and
                type(tick) in (int, float) and math.isfinite(tick) and tick >= 0 and
                (self.last is None or (wall >= self.last[0] and tick >= self.last[1])))
        except Exception:
            valid = False
        if not valid:
            self.errors.add('diagnostic-clock-invalid'); return None
        self.last = (wall, tick); return self.last

    def report(self):
        rows = deepcopy(self.rows)
        for row in rows:
            for source, target in (('startedAtMs','remainingAtStartMs'),('finishedAtMs','remainingAtEndMs')):
                row[target] = (self.deadline-row[source]
                    if self.deadline is not None and row[source] is not None else None)
        return dict(format=VERSION, valid=not self.errors, diagnosticCodes=sorted(self.errors),
            originalDeadlineMs=self.deadline, sendGuardAtMs=self.send_guard,
            sendGuardRemainingMs=None if self.deadline is None or self.send_guard is None else self.deadline-self.send_guard,
            spans=rows, maximumSpans=MAX_SPANS, diagnosticOnly=True,
            extendsDeadline=False, authorizesExecution=False,
            basis='Inclusive local phase durations; completion is control flow, not transaction success or finality.')


@contextmanager
def capture(profile):
    if type(profile) is not Profile or profile.used or _current.get() is not None:
        raise ValueError('entry-profile-scope-unavailable')
    profile.used = True; token = _current.set(profile)
    try: yield profile
    finally: _current.reset(token)


@contextmanager
def measure(name):
    p = _current.get()
    if p is None:
        yield; return
    known = type(name) is str and name in STAGES
    if not known or len(p.rows) >= MAX_SPANS:
        p.errors.add('diagnostic-span-invalid' if not known else 'diagnostic-span-cap')
        yield; return
    start = p.sample()
    row = dict(stage=name, parentStage=p.stack[-1] if p.stack else None,
        startedAtMs=None if start is None else start[0],
        finishedAtMs=None, elapsedMs=None, completed=False)
    p.rows.append(row); p.stack.append(name)
    complete = False
    try:
        yield; complete = True
    finally:
        p.stack.pop()
        end = p.sample()
        if end is not None: row['finishedAtMs'] = end[0]
        if start is not None and end is not None:
            elapsed = (end[1]-start[1])*1000
            if math.isfinite(elapsed) and elapsed >= 0:
                row['elapsedMs'] = round(elapsed, 3)
                row['completed'] = complete
            else:
                p.errors.add('diagnostic-clock-invalid')


def pin_deadline(value):
    p = _current.get()
    if p is None: return
    if type(value) is not int or not 0 < value < 2**53 or (p.deadline is not None and p.deadline != value):
        p.errors.add('diagnostic-deadline-invalid'); return
    p.deadline = value


def record_send_guard(at_ms):
    p = _current.get()
    if p is None: return
    if (type(at_ms) is not int or p.deadline is None or not 0 < at_ms < p.deadline or
            p.send_guard is not None):
        p.errors.add('diagnostic-send-guard-invalid'); return
    p.send_guard = at_ms
