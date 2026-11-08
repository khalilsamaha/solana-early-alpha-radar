"""Bounded span instrumentation for the disposable successor rehearsal only."""
from contextlib import contextmanager, ExitStack
from functools import wraps
import sys
import threading
import time
from unittest.mock import patch

VERSION = 'successor-phase-cost-1'
MAX_SPANS = 4096
STAGES = frozenset(('execution', 'collect-sign', 'collect-persist', 'collector',
    'signing-handoff', 'signer-backend', 'submit', 'transport-load', 'handoff-load',
    'current-binding', 'lifecycle', 'retirement-context', 'successor-validation',
    'successor-binding', 'preparation-replay', 'journal-open', 'transport-replay',
    'transport-append', 'send-rpc', 'preflight-rpc', 'transaction-enter',
    'transaction-commit', 'transaction-rollback'))
_lock = threading.Lock()


class Profile:
    def __init__(self, *, tick=time.perf_counter_ns, cpu=time.thread_time_ns,
                 wall=lambda: time.time_ns() // 1000000):
        self.tick, self.cpu, self.wall = tick, cpu, wall
        self.rows, self.stack, self.errors = [], [], set()

    def sample(self):
        try:
            value = (self.tick(), self.cpu(), self.wall())
            if all(type(x) is int and x >= 0 for x in value):
                return value
        except Exception:
            pass
        self.errors.add('diagnostic-clock-invalid')
        return None

    @contextmanager
    def measure(self, stage):
        if stage not in STAGES or len(self.rows) >= MAX_SPANS:
            self.errors.add('diagnostic-stage-invalid' if stage not in STAGES else 'diagnostic-span-cap')
            yield
            return
        start = self.sample()
        row = dict(stage=stage, parentIndex=self.stack[-1] if self.stack else None,
                   startedAtMs=None if start is None else start[2], finishedAtMs=None,
                   elapsedMs=None, threadCpuMs=None, completed=False)
        index = len(self.rows)
        self.rows.append(row)
        self.stack.append(index)
        try:
            yield
            row['completed'] = True
        finally:
            self.stack.pop()
            end = self.sample()
            if end is not None:
                row['finishedAtMs'] = end[2]
            if start is not None and end is not None:
                if all(b >= a for a, b in zip(start, end)):
                    row.update(elapsedMs=(end[0]-start[0])/1000000,
                               threadCpuMs=(end[1]-start[1])/1000000)
                else:
                    self.errors.add('diagnostic-clock-invalid')

    def report(self, deadline=None):
        rows = [dict(row) for row in self.rows]
        children = [[] for _ in rows]
        for row in rows:
            if row['parentIndex'] is not None:
                children[row['parentIndex']].append(row)
        totals = {}
        for index, row in enumerate(rows):
            for name, exclusive in (('elapsedMs', 'exclusiveMs'), ('threadCpuMs', 'exclusiveThreadCpuMs')):
                values = [child[name] for child in children[index]]
                row[exclusive] = (None if row[name] is None or any(v is None for v in values)
                                  else max(0., row[name]-sum(values)))
            row['headroomAtEndMs'] = (None if deadline is None or row['finishedAtMs'] is None
                                       else deadline-row['finishedAtMs'])
            group = totals.setdefault(row['stage'], dict(calls=0, incomplete=0,
                elapsedMs=0., exclusiveMs=0., threadCpuMs=0., exclusiveThreadCpuMs=0.))
            group['calls'] += 1
            group['incomplete'] += not row['completed']
            for name in ('elapsedMs', 'exclusiveMs', 'threadCpuMs', 'exclusiveThreadCpuMs'):
                group[name] = None if group[name] is None or row[name] is None else group[name]+row[name]
                if row[name] is not None:
                    row[name] = round(row[name], 3)
        for group in totals.values():
            for name in ('elapsedMs', 'exclusiveMs', 'threadCpuMs', 'exclusiveThreadCpuMs'):
                if group[name] is not None:
                    group[name] = round(group[name], 3)
        return dict(valid=not self.errors and not self.stack, diagnosticCodes=sorted(self.errors),
                    maximumSpans=MAX_SPANS, spans=rows, stageTotals=totals)


def timed(fn, profile, stage):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        label = stage(*args, **kwargs) if callable(stage) else stage
        with profile.measure(label):
            return fn(*args, **kwargs)
    return wrapped


def transaction(fn, profile):
    @contextmanager
    def wrapped(self, *args, **kwargs):
        cm = fn(self, *args, **kwargs)
        with profile.measure('transaction-enter'):
            value = cm.__enter__()
        try:
            yield value
        except BaseException:
            with profile.measure('transaction-rollback'):
                suppressed = cm.__exit__(*sys.exc_info())
            if not suppressed:
                raise
        else:
            with profile.measure('transaction-commit'):
                cm.__exit__(None, None, None)
    return wrapped


@contextmanager
def instrument(profile, execution):
    """Install patches only inside the measured disposable first-attempt phase."""
    m = execution
    signing, transport = m.signing, m.submission
    handoff, successor = signing.handoff, signing.successor
    import journal
    targets = [
        (m, '_collect_sign_submit', 'execution'),
        (signing, '_collect_sign', 'collect-sign'),
        (successor, '_prepare_from_producer', 'collect-persist'),
        (signing.collection.Collector, '__call__', 'collector'),
        (handoff, '_dispatch', 'signing-handoff'),
        (signing.backend, '_invoke', 'signer-backend'),
        (transport, '_submit', 'submit'),
        (transport, 'load', 'transport-load'),
        (handoff, 'load', 'handoff-load'),
        (handoff, 'current', 'current-binding'),
        (successor.history.lifecycle, '_projection', 'lifecycle'),
        (successor.retirement, 'position_context', 'retirement-context'),
        (successor, 'validate', 'successor-validation'),
        (successor, 'binding', 'successor-binding'),
        (successor.preparation, 'saved', 'preparation-replay'),
        (transport.transport, '_open', 'journal-open'),
        (transport, 'replay', 'transport-replay'),
        (transport, 'append', 'transport-append'),
        (transport.transport.SendRpc, 'request',
         lambda self, method, *a, **kw: 'send-rpc' if method == 'sendTransaction' else 'preflight-rpc'),
    ]
    with ExitStack() as stack:
        for obj, name, stage in targets:
            stack.enter_context(patch.object(obj, name, timed(getattr(obj, name), profile, stage)))
        stack.enter_context(patch.object(journal.Journal, 'transaction', transaction(journal.Journal.transaction, profile)))
        yield


def run():
    if not _lock.acquire(blocking=False):
        raise ValueError('offline-profile-busy')
    try:
        import successor_execution_checks as checks
        profile = Profile()
        phase = checks.fixture.phase
        measured = 0

        @contextmanager
        def observed(report, name):
            nonlocal measured
            with phase(report, name) as row:
                if name == 'collection-signing-preflight-single-send':
                    measured += 1
                    with instrument(profile, checks.m):
                        yield row
                else:
                    yield row

        with patch.object(checks.fixture, 'phase', observed):
            rehearsal = checks.run()
        data = profile.report((rehearsal.get('integration') or {}).get('originalDeadlineMs'))
        complete = measured == 1 and bool(data['spans']) and data['valid']
        return dict(format=VERSION, state='diagnostic-collected' if complete else 'diagnostic-incomplete',
            profile=data, rehearsal=rehearsal, measuredPhases=measured,
            timingAcceptance=False, fullAcceptanceSuiteRun=False, executionApproved=False,
            limitations=[
                'Only the first connected 1 MiB attempt is instrumented; setup and recovery remain outside the spans.',
                'Real clocks and original deadlines are unchanged. Instrumentation can itself cause expiry.',
                'A diagnostic-collected state means usable timings, not execution or timing acceptance.',
                'This runs the connected rehearsal, not the separate 27 preliminary acceptance tests.',
                'Nested inclusive times overlap; exclusive time excludes directly recorded children only.',
                'Thread CPU excludes child processes. Wall minus thread CPU is not proof of disk or scheduler delay.',
                'No arguments, SQL, transaction bytes, keys, arbitrary exceptions or source paths are exported.'])
    finally:
        _lock.release()
