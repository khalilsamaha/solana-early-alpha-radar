"""Opt-in, bounded canonical SHA-256 reuse; no validation result is cached."""
from contextlib import contextmanager
from collections import OrderedDict
from contextvars import ContextVar
from functools import wraps
import json
import hashlib
import sys

VERSION = 'exact-canonical-digest-1'
MAX_ENTRIES = 128
MAX_BYTES = 32 * 1024 * 1024
MAX_ENTRY_BYTES = 16 * 1024 * 1024
MAX_NODES = 8192
MAX_DEPTH = 48
_SCOPE = ContextVar('exact_canonical_digest', default=None)


class Ineligible(Exception):
    pass


def original(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def frozen(value):
    """Exact typed content, not identity or digest. Never retain mutable inputs.

    Unsupported types and excessive traversal bypass reuse, not serialization.
    A generous per-node allowance includes tuple/key/table bookkeeping; strings
    are counted at their full Python allocation size even when shared.
    """
    nodes = 0
    size = 0
    active = set()

    def visit(item, depth):
        nonlocal nodes, size
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise Ineligible
        kind = type(item)
        if kind not in (str, int, bool, type(None), list, dict):
            raise Ineligible
        size += 256 + (sys.getsizeof(item) if kind in (str, int) else 0)
        if size > MAX_ENTRY_BYTES:
            raise Ineligible
        if kind is str:
            return ('s', item)
        if kind is bool:
            return ('b', item)
        if item is None:
            return ('n',)
        if kind is int:
            if item.bit_length() > 256:
                raise Ineligible
            return ('i', item)
        if id(item) in active or len(item) > MAX_NODES:
            raise Ineligible
        active.add(id(item))
        try:
            if kind is list:
                return ('l', tuple(visit(x, depth + 1) for x in item))
            if any(type(k) is not str for k in item):
                raise Ineligible
            return ('d', tuple((visit(k, depth + 1), visit(item[k], depth + 1))
                               for k in sorted(item)))
        finally:
            active.remove(id(item))

    key = visit(value, 0)
    return key, size


def materialize(key):
    """Serialize only the immutable key's content, never a concurrently edited input."""
    tag = key[0]
    if tag == 'n':
        return None
    if tag == 'l':
        return [materialize(x) for x in key[1]]
    if tag == 'd':
        return {materialize(k): materialize(v) for k, v in key[1]}
    return key[1]


@contextmanager
def scope(*, enabled=True):
    if type(enabled) is not bool:
        raise ValueError('canonical-scope-mode')
    values = OrderedDict()
    counts = dict(calls=0, hits=0, computations=0, capacityBypasses=0,
                  ineligibleBypasses=0, failures=0, retainedBytes=0, evictions=0)
    token = _SCOPE.set((values, counts) if enabled else None)

    def snapshot():
        return dict(version=VERSION, enabled=enabled, **counts,
                    entries=len(values), maximumEntries=MAX_ENTRIES,
                    maximumRetainedBytes=MAX_BYTES,
                    reusesValidationOrAuthorization=False, rechecksFullInputContent=True)
    try:
        yield snapshot
    finally:
        values.clear()
        counts['retainedBytes'] = 0
        _SCOPE.reset(token)


def digest(value):
    current = _SCOPE.get()
    if current is None:
        return original(value)
    values, counts = current
    counts['calls'] += 1
    try:
        key, key_size = frozen(value)
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
    retained = key_size + sys.getsizeof(result)
    if retained > MAX_ENTRY_BYTES or retained > MAX_BYTES:
        counts['capacityBypasses'] += 1
        return result
    while values and (len(values) >= MAX_ENTRIES or counts['retainedBytes'] + retained > MAX_BYTES):
        _, (_, removed) = values.popitem(last=False)
        counts['retainedBytes'] -= removed
        counts['evictions'] += 1
    values[key] = (result, retained)
    counts['retainedBytes'] += retained
    return result


def operation(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with scope() as statistics:
            result = fn(*args, **kwargs)
            result['canonicalDigestReplay'] = statistics()
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
                  retainedBytes=MAX_BYTES, entries=MAX_ENTRIES)
    if any(type(value.get(k)) is not int or not 0 <= value[k] <= cap for k, cap in limits.items()):
        return None
    if (type(value.get('maximumEntries')) is not int or value['maximumEntries'] != MAX_ENTRIES or
            type(value.get('maximumRetainedBytes')) is not int or value['maximumRetainedBytes'] != MAX_BYTES):
        return None
    return dict(version=VERSION, enabled=value['enabled'], **{k:value[k] for k in limits},
                maximumEntries=MAX_ENTRIES, maximumRetainedBytes=MAX_BYTES,
                reusesValidationOrAuthorization=False, rechecksFullInputContent=True)
