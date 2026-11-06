"""Bounded collection telemetry; never used for deadlines or authorization."""
import math
import time

VERSION = 'exit-collection-diagnostics-1'
STAGES = ('admission', 'pool', 'packet', 'accounts', 'simulation',
          'final-binding', 'preserved-validation', 'complete')
CODES = {'exit-capture-admission-stopped','exit-capture-source-changed','exit-capture-already-prepared',
                 'exit-capture-admission-changed','exit-capture-expired','exit-capture-time-budget',
                 'exit-capture-stopped','exit-capture-simulation','exit-capture-initial-pool',
                 'continuation-limit-reached','replacement-stopped','replacement-limit-reached','replacement-unknown-schema',
                 'replacement-signing-or-later-evidence','replacement-backend-marker',
                 'preserved-exit-read-only-required','preserved-exit-stopped','preserved-exit-schema',
                 'preserved-exit-later-evidence','preserved-exit-backend-marker',
                 'preserved-exit-original-mismatch','preserved-exit-replacement-required',
                 'preserved-exit-current-mismatch','preserved-exit-not-expired',
                 'preserved-exit-validation-expired','preserved-exit-time-budget','exit-collection-expired',
                 'replacement-original-mismatch','replacement-original-not-expired','replacement-expected-identity'}
CODES.add('exit-evidence-unavailable')


def number(value):
    return type(value) in (int, float) and 0 <= value <= 3600000 and math.isfinite(value)


class Timing:
    """Independent perf clock. Telemetry failure withholds timings, never changes guards."""
    def __init__(self):
        self.rows = []; self.stage = 'admission'; self.bad = False
        self.started = self.last = self.tick()

    def tick(self):
        try:
            value = time.perf_counter_ns()
            if type(value) is not int or value < 0: raise ValueError('clock')
            return value
        except Exception:
            self.bad = True
            return None

    def mark(self, stage):
        now = self.tick()
        if (self.bad or stage not in STAGES or len(self.rows) >= len(STAGES)
                or self.last is None or now is None or now < self.last):
            self.bad = True
        else:
            elapsed = (now - self.last) / 1000000
            if not number(elapsed): self.bad = True
            else: self.rows.append(dict(stage=self.stage, elapsedMs=round(elapsed, 3)))
        self.stage = stage; self.last = now

    def finish(self):
        self.mark(self.stage)
        if self.bad or self.started is None or self.last is None: return None
        elapsed = (self.last - self.started) / 1000000
        if not number(elapsed): return None
        return dict(version=VERSION, elapsedMs=round(elapsed, 3), stages=self.rows,
                    basis='local-monotonic-elapsed-including-rpc-and-validation')


def summary(raw):
    """Allowlisted public evidence only, including when collection failed."""
    if type(raw) is not dict: return None
    state = raw.get('state'); stage = raw.get('stage'); code = raw.get('diagnosticCode')
    out = dict(state=state if type(state) is str and state in ('unavailable', 'exit-evidence-collected-research-only') else 'unclassified',
        stage=stage if type(stage) is str and stage in STAGES else 'unclassified',
        diagnosticCode=None if code is None else code if type(code) is str and code in CODES else 'exit-evidence-unavailable')
    n = raw.get('networkRequests')
    out['networkRequests'] = n if type(n) is int and 0 <= n <= 20 else None
    t = raw.get('collectionTiming'); out['collectionTiming'] = None
    if type(t) is dict and t.get('version') == VERSION and number(t.get('elapsedMs')):
        rows = t.get('stages')
        if type(rows) is list and len(rows) <= len(STAGES) and all(type(r) is dict and
                type(r.get('stage')) is str and r['stage'] in STAGES and number(r.get('elapsedMs')) for r in rows):
            out['collectionTiming'] = dict(version=VERSION, elapsedMs=t['elapsedMs'],
                stages=[dict(stage=r['stage'], elapsedMs=r['elapsedMs']) for r in rows],
                basis='local-monotonic-elapsed-including-rpc-and-validation')
    return out
