"""Bounded offline rehearsal diagnostics, never an execution clock or permission."""
from contextlib import contextmanager
import math
from pathlib import Path
import re
import traceback
import time

VERSION='continuation-rehearsal-diagnostics-1'
PHASES=frozenset(('connected-rehearsal','fixture-class-setup','fixture-instance-setup','entry-collection','entry-settlement',
    'continuation-collection-persistence','continuation-signing-handoff','continuation-submission',
    'original-preparation','original-expiry-wait','replacement-preparation','replacement-expiry-wait',
    'predecessor-snapshot','continuation-fixture-inputs','continuation-sign-send','connected-assertions',
    'preserved-records','independent-contract','repeat-refusal-recovery','repeated-recovery','fixture-cleanup'))
CODES=frozenset(('canonical-digest-reuse-missing','synthetic-program-size','original-not-prepared','previous-not-prepared','temporary-scope',
    'exit-capture-expired','exit-capture-time-budget','exit-capture-stopped','exit-capture-simulation',
    'exit-capture-initial-pool','exit-capture-source-changed','exit-capture-admission-changed',
    'exit-collection-expired','exit-evidence-unavailable','exit-preparation-expired',
    'replacement-expired-before-write','replacement-expired-before-commit',
    'continuation-expired-before-write','continuation-expired-before-commit',
    'fresh-signing-expired','fresh-signing-clock','fresh-signing-monotonic','fresh-signing-stopped',
    'fresh-exit-not-created','fresh-exit-signing-unavailable','fresh-exit-continuation-identity',
    'exit-signing-expired','exit-signing-boundary-expired-or-stopped','fresh-exit-evidence-unavailable',
    'rehearsal-unknown-send','rehearsal-one-send','rehearsal-original-expiry','rehearsal-request-count',
    'continuation-signing-evidence','continuation-lineage','predecessor-records-mutated',
    'independent-contract-cases','source-mutated','repeat-attempt','recovery-not-observation',
    'repeat-send','repeated-recovery-mutated','repeated-recovery-send'))
STATES=frozenset(('unavailable','inspection-required','exit-prepared-research-only',
    'exit-signed-recorded',
    'exit-preparation-expired','exit-preparation-stopped','exit-evidence-collected-research-only',
    'fresh-exit-inspection-required','exit-submission-unknown','rpc-acknowledged',
    'entry-position-open','entry-settled-exit-not-prepared','exit-finalized-evidence'))
TYPES=frozenset(('ValueError','AssertionError','KeyError','TypeError','OSError','RuntimeError',
    'TimeoutError','CalledProcessError','TimeoutExpired','OperationalError','IntegrityError'))


def code(value):
    return value if type(value) is str and value in CODES else 'unclassified'


def observation(result):
    """Never copy arbitrary keys, error text, identifiers, wires, or fixture paths."""
    if type(result) is not dict:return dict(resultType='non-object')
    value=result.get('state');r=dict(state=value if type(value) is str and value in STATES else 'unclassified')
    if result.get('diagnosticCode') is not None:r['diagnosticCode']=code(result['diagnosticCode'])
    for key in ('createdThisRun','collectionRecorded','accountingUsable','completedWithinOriginalDeadline'):
        if type(result.get(key)) is bool:r[key]=result[key]
    for key in ('networkRequests','collectionRequestsThisRun','collectionRequests','senderRequests','sendRequestsThisRun','signerInvocationAttempts'):
        value=result.get(key)
        if type(value) is int and 0<=value<=100:r[key]=value
    return r


def locations(exc):
    """Only code coordinates in this checked-out module directory; never locals,
    source lines, exception values, user directories or complete filesystem paths.
    """
    root=Path(__file__).resolve().parent;rows=[]
    for frame,line in traceback.walk_tb(exc.__traceback__):
        file=Path(frame.f_code.co_filename)
        if file.resolve().parent!=root:continue
        name=frame.f_code.co_name
        if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]{0,79}\.py',file.name):continue
        if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]{0,79}',name):continue
        if type(line) is not int or not 0<line<=1000000:continue
        rows.append(dict(module=file.name,function=name,line=line))
    return rows[-8:]


@contextmanager
def phase(report,name,*,monotonic=time.monotonic):
    if name not in PHASES:raise ValueError('invalid-diagnostic-phase')
    rows=report.setdefault('diagnosticPhases',[])
    if len(rows)>=32:raise ValueError('diagnostic-phase-cap')
    row=dict(phase=name,completed=False,elapsedMs=None);rows.append(row)
    report['diagnosticsVersion']=VERSION;report['lastPhase']=name
    start=monotonic()
    try:
        yield row
        row['completed']=True
    except Exception as exc:
        row['errorType']=type(exc).__name__ if type(exc).__name__ in TYPES else 'unclassified'
        # Exact known codes only, including the exception type. Never stringify
        # arbitrary exception payloads or include assertion/RPC/Node stderr.
        row['diagnosticCode']=code(exc.args[0]) if type(exc) is ValueError and len(exc.args)==1 else 'unclassified'
        row['codeLocations']=locations(exc)
        report.setdefault('failedPhase',name)
        raise
    finally:
        end=monotonic()
        if type(start) in (int,float) and type(end) in (int,float) and math.isfinite(start) and math.isfinite(end) and end>=start:
            row['elapsedMs']=round((end-start)*1000,3)
