"""Opt-in exact canonical JSON text reuse; no validation result is cached.

Only continuation owns this scope. Journal reads and checks still run. A full
typed immutable snapshot keys each lookup; callers never receive cached mutable
objects. The shared freezer preserves the digest cache's input restrictions.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import json
import sys
from canonical_replay import Entries, Ineligible, frozen, materialize, MAX_NODES, SHARED_STRING_MIN

VERSION = 'exact-canonical-text-1'
MAX_ENTRIES = 128
MAX_BYTES = 48 * 1024 * 1024
MAX_ENTRY_BYTES = 16 * 1024 * 1024
_SCOPE = ContextVar('exact_canonical_text', default=None)


def original(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def statistics(values, counts, enabled=True):
    return dict(version=VERSION, enabled=enabled, **counts,
                entries=len(values), maximumEntries=MAX_ENTRIES,
                maximumRetainedBytes=MAX_BYTES,
                sharedStrings=len(values.strings),
                sharedStringBytes=sum(row[2] for row in values.strings.values()),
                sharedStringReferences=sum(row[1] for row in values.strings.values()),
                reusesValidationOrAuthorization=False, rechecksFullInputContent=True)


@contextmanager
def scope(*, enabled=True):
    if type(enabled) is not bool:
        raise ValueError('canonical-scope-mode')
    values = Entries()
    counts = dict(calls=0, hits=0, computations=0, capacityBypasses=0,
                  ineligibleBypasses=0, failures=0, retainedBytes=0, evictions=0)
    token = _SCOPE.set((values, counts) if enabled else None)

    try:
        yield lambda: statistics(values, counts, enabled)
    finally:
        values.clear()
        counts['retainedBytes'] = 0
        _SCOPE.reset(token)


def encoded(value):
    current = _SCOPE.get()
    if current is None:
        return original(value)
    values, counts = current
    counts['calls'] += 1
    try:
        matched=values.find_exact(value)
    except (RuntimeError,KeyError,IndexError):
        counts['ineligibleBypasses'] += 1
        return original(value)
    if matched is not None:
        key,result=matched
        counts['hits'] += 1
        values.move_to_end(key)
        return result
    try:
        key, key_size, structural, atoms = frozen(value, values.strings)
    except (Ineligible, RuntimeError, KeyError):
        counts['ineligibleBypasses'] += 1
        return original(value)
    cached = values.get(key)
    if cached is not None:
        counts['hits'] += 1
        values.move_to_end(key)
        return cached[0]
    counts['computations'] += 1
    try:
        result = original(materialize(key))
    except BaseException:
        counts['failures'] += 1
        raise
    # Entry tuple, atom-reference tuple and OrderedDict/index bookkeeping are
    # charged in addition to the per-node frozen-tree allowance.
    structural += sys.getsizeof(result) + 2048
    if key_size + sys.getsizeof(result) > MAX_ENTRY_BYTES or values.additional_bytes(structural, atoms) > MAX_BYTES:
        counts['capacityBypasses'] += 1
        return result
    while values and (len(values) >= MAX_ENTRIES or
                      counts['retainedBytes'] + values.additional_bytes(structural, atoms) > MAX_BYTES):
        counts['retainedBytes'] -= values.remove_oldest()
        counts['evictions'] += 1
    if counts['retainedBytes'] + values.additional_bytes(structural, atoms) > MAX_BYTES:
        counts['capacityBypasses'] += 1
        return result
    counts['retainedBytes'] += values.remember(key, result, structural, atoms)
    return result


def operation(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        reuse = kwargs.pop('_reuse_serialization_scope', False)
        if type(reuse) is not bool: raise ValueError('computation-scope-mode')
        current = _SCOPE.get()
        if reuse and current is not None:
            result = fn(*args, **kwargs)
            result['canonicalTextReplay'] = statistics(*current)
            return result
        with scope() as snapshot:
            result = fn(*args, **kwargs)
            result['canonicalTextReplay'] = snapshot()
            return result
    return wrapped


def summary(value):
    """Bounded diagnostics only; never copy retained inputs or arbitrary text."""
    if type(value) is not dict or value.get('version') != VERSION:
        return None
    if (type(value.get('enabled')) is not bool or
            value.get('reusesValidationOrAuthorization') is not False or
            value.get('rechecksFullInputContent') is not True):
        return None
    limits = dict(calls=10_000_000, hits=10_000_000, computations=10_000_000,
                  capacityBypasses=10_000_000, ineligibleBypasses=10_000_000,
                  failures=10_000_000, evictions=10_000_000,
                  retainedBytes=MAX_BYTES, entries=MAX_ENTRIES,
                  sharedStrings=MAX_BYTES // SHARED_STRING_MIN,
                  sharedStringBytes=MAX_BYTES, sharedStringReferences=MAX_NODES * MAX_ENTRIES)
    if any(type(value.get(k)) is not int or not 0 <= value[k] <= cap for k, cap in limits.items()):
        return None
    if (type(value.get('maximumEntries')) is not int or value['maximumEntries'] != MAX_ENTRIES or
            type(value.get('maximumRetainedBytes')) is not int or value['maximumRetainedBytes'] != MAX_BYTES):
        return None
    return dict(version=VERSION, enabled=value['enabled'], **{k:value[k] for k in limits},
                maximumEntries=MAX_ENTRIES, maximumRetainedBytes=MAX_BYTES,
                reusesValidationOrAuthorization=False, rechecksFullInputContent=True)
