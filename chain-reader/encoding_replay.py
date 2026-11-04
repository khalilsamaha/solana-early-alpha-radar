"""Bounded exact public encoding reuse inside one opt-in operation.

No ledger, file, account state, signature verdict, clock or authorization is cached.
Only immutable results of exact immutable inputs are retained, then discarded.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

VERSION = 'exact-public-encoding-1'
MAX_ENTRIES = 512
_SCOPE = ContextVar('exact_public_encoding', default=None)
_KINDS = {
    'identifier32': (str, 90, str, 90),
    'identifier64': (str, 90, str, 90),
    'encode': (bytes, 64, str, 90),
    'decode': (str, 90, bytes, 66),
}


@contextmanager
def scope(*, enabled=True):
    if type(enabled) is not bool:
        raise ValueError('encoding-scope-mode')
    values = {}
    counts = dict(calls=0, hits=0, computations=0, capacityBypasses=0,
                  ineligibleBypasses=0, failures=0)
    token = _SCOPE.set((values, counts) if enabled else None)
    def snapshot():
        return dict(version=VERSION, enabled=enabled, **counts,
                    entries=len(values), maximumEntries=MAX_ENTRIES,
                    storesStateOrAuthorization=False)
    try:
        yield snapshot
    finally:
        values.clear()
        _SCOPE.reset(token)


def replay(kind, value, compute):
    current = _SCOPE.get()
    if current is None:
        return compute()
    values, counts = current
    counts['calls'] += 1
    spec = _KINDS.get(kind) if type(kind) is str else None
    if spec is None or type(value) is not spec[0] or len(value) > spec[1]:
        counts['ineligibleBypasses'] += 1
        return compute()
    key = (kind, value)
    if key in values:
        counts['hits'] += 1
        return values[key]
    counts['computations'] += 1
    try:
        result = compute()
    except BaseException:
        counts['failures'] += 1
        raise
    # Preserve the original return/exception behavior even for unexpected types;
    # only the fixed small immutable outputs are eligible for storage.
    if type(result) is spec[2] and len(result) <= spec[3]:
        if len(values) < MAX_ENTRIES:
            values[key] = result
        else:
            counts['capacityBypasses'] += 1
    return result


def operation(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with scope() as statistics:
            result = fn(*args, **kwargs)
            result['encodingReplay'] = statistics()
            return result
    return wrapped
