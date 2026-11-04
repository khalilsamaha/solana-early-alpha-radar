"""Operation-local reuse of exact immutable admission-chain validation.

SQL rows are fetched on every call. No authorization, balance, clock, source-file
identity or live evidence is memoized. Mutable results are reconstructed on hits.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import json

VERSION='exact-admission-history-1'
MAX_ENTRIES=32
MAX_ROWS=64
MAX_ENTRY_BYTES=256*1024
MAX_TOTAL_BYTES=2*1024*1024
_SCOPE=ContextVar('exact_admission_history',default=None)


@contextmanager
def scope(*,enabled=True):
    if type(enabled) is not bool:raise ValueError('history-scope-mode')
    values={};counts=dict(calls=0,hits=0,validations=0,bypasses=0,failures=0,retainedBytes=0)
    token=_SCOPE.set((values,counts) if enabled else None)
    def statistics():
        return dict(version=VERSION,enabled=enabled,**counts,entries=len(values),
            maximumEntries=MAX_ENTRIES,maximumRetainedBytes=MAX_TOTAL_BYTES,
            sqlReadsSkipped=0,authorizationDecisionsCached=False)
    try:yield statistics
    finally:
        values.clear();counts['retainedBytes']=0;_SCOPE.reset(token)


def replay(policy,rows,compute):
    current=_SCOPE.get()
    if current is None:return compute()
    values,counts=current;counts['calls']+=1
    # Exact built-in immutable inputs only; unusual or large inputs retain the
    # original validator's behavior and cannot occupy unbounded operation memory.
    if not 0<len(rows)<=MAX_ROWS:
        counts['bypasses']+=1;return compute()
    policy_text=json.dumps(policy,sort_keys=True,separators=(',', ':'),allow_nan=False)
    if len(policy_text)>65536:
        counts['bypasses']+=1;return compute()
    key_rows=[];size=len(policy_text.encode())
    for row in rows:
        item=tuple(row[k] for k in ('seq','at_ms','value','previous_hash','hash'))
        if (any(type(x) is not int for x in item[:2]) or any(type(x) is not str for x in item[2:]) or
                any(len(x)>MAX_ENTRY_BYTES for x in item[2:])):
            counts['bypasses']+=1;return compute()
        size+=32+sum(len(x.encode()) for x in item[2:])
        if size>MAX_ENTRY_BYTES:
            counts['bypasses']+=1;return compute()
        key_rows.append(item)
    key=(policy_text,tuple(key_rows))
    if key in values:
        counts['hits']+=1
        state,count,head,stamp=values[key]
        return json.loads(state),count,head,stamp
    counts['validations']+=1
    try:result=compute()
    except BaseException:
        counts['failures']+=1;raise
    # The trusted validator checks canonical JSON and returns the last row's state.
    # Retain only immutable row text, never its mutable decoded result.
    if len(values)<MAX_ENTRIES and counts['retainedBytes']+size<=MAX_TOTAL_BYTES:
        values[key]=(key_rows[-1][2],result[1],result[2],result[3])
        counts['retainedBytes']+=size
    else:counts['bypasses']+=1
    return result


def operation(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        with scope() as statistics:
            result=fn(*args,**kwargs)
            result['admissionHistoryReplay']=statistics()
            return result
    return wrapped
