"""Opt-in, bounded canonical SHA-256 reuse; no validation result is cached."""
from contextlib import contextmanager
from collections import OrderedDict
from contextvars import ContextVar
from functools import wraps
import json
import hashlib
import sys

VERSION = 'exact-canonical-digest-3'
MAX_ENTRIES = 128
MAX_BYTES = 32 * 1024 * 1024
MAX_ENTRY_BYTES = 16 * 1024 * 1024
MAX_NODES = 8192
MAX_DEPTH = 48
SHARED_STRING_MIN = 4096
_SCOPE = ContextVar('exact_canonical_digest', default=None)


class Ineligible(Exception):
    pass


def original(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def frozen(value, shared):
    """Exact typed content, not identity or digest. Never retain mutable inputs.

    Unsupported types and excessive traversal bypass reuse, not serialization.
    The original full-size per-input cap still applies. Equal large immutable
    strings may share storage across retained keys; no mutable object is shared.
    Return structural bytes separately from the deduplicated string references.
    """
    nodes = 0
    size = 0
    shared_bytes = 0
    atoms = {}
    active = set()

    def visit(item, depth):
        nonlocal nodes, size, shared_bytes
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
            if len(item) >= SHARED_STRING_MIN:
                shared_bytes += sys.getsizeof(item)
                canonical = atoms.get(item)
                if canonical is None:
                    stored = shared.get(item)
                    canonical = item if stored is None else stored[0]
                    atoms[canonical] = canonical
                return ('s', canonical)
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
    return key, size, size - shared_bytes, tuple(atoms)


def bucket(value):
    """Small candidate index only. It is never sufficient to accept a hit."""
    if type(value) is not dict or len(value)>32:
        return None
    if any(type(k) is not str or len(k)>128 for k in value):
        return None
    label=value.get('format')
    return (tuple(sorted(value)),label if type(label) is str and len(label)<=128 else None)


def frozen_bucket(key):
    if key[0]!='d' or len(key[1])>32:
        return None
    keys=[];label=None
    for k,v in key[1]:
        if len(k[1])>128:return None
        keys.append(k[1])
        if k[1]=='format' and v[0]=='s' and len(v[1])<=128:label=v[1]
    return (tuple(keys),label)


def exact_match(value,key):
    """Compare every current value/type with a bounded immutable snapshot.

    No mutable identity shortcut, hash-only equality, sorting of nested objects,
    new snapshot or validation verdict. The stored tree bounds recursion even
    when the current input is cyclic. Unsupported types cannot match.
    """
    tag=key[0];kind=type(value)
    if tag=='s':return kind is str and value==key[1]
    if tag=='i':return kind is int and value==key[1]
    if tag=='b':return kind is bool and value==key[1]
    if tag=='n':return value is None
    if tag=='l':
        return kind is list and len(value)==len(key[1]) and all(
            exact_match(value[i],k) for i,k in enumerate(key[1])) and len(value)==len(key[1])
    if kind is not dict or len(value)!=len(key[1]) or any(type(k) is not str for k in value):
        return False
    return all(k[1] in value and exact_match(value[k[1]],v) for k,v in key[1]) and len(value)==len(key[1])


class Entries(OrderedDict):
    """Scope-local storage: shared strings live only while a retained key uses them."""
    def __init__(self):
        super().__init__()
        self.strings = {}
        self.buckets = {}

    def find_exact(self, value):
        index=bucket(value)
        if index is None:return None
        for key in self.buckets.get(index, ()):
            if exact_match(value,key):
                return key,self[key][0]
        return None

    def additional_bytes(self, structural, atoms):
        # Conservative allowance for each shared dictionary entry and refcount.
        return structural + sum(sys.getsizeof(s) + 512 for s in atoms if s not in self.strings)

    def remove_oldest(self):
        key, (_, structural, atoms) = self.popitem(last=False)
        index=frozen_bucket(key)
        if index is not None:
            keys=self.buckets[index];keys.remove(key)
            if not keys:del self.buckets[index]
        removed = structural
        for s in atoms:
            row = self.strings[s]
            row[1] -= 1
            if row[1] == 0:
                removed += row[2]
                del self.strings[s]
        return removed

    def remember(self, key, result, structural, atoms):
        additional = self.additional_bytes(structural, atoms)
        for s in atoms:
            if s in self.strings:
                self.strings[s][1] += 1
            else:
                self.strings[s] = [s, 1, sys.getsizeof(s) + 512]
        self[key] = (result, structural, atoms)
        index=frozen_bucket(key)
        if index is not None:self.buckets.setdefault(index,[]).append(key)
        return additional

    def clear(self):
        super().clear()
        self.strings.clear()
        self.buckets.clear()


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
    values = Entries()
    counts = dict(calls=0, hits=0, computations=0, capacityBypasses=0,
                  ineligibleBypasses=0, failures=0, retainedBytes=0, evictions=0)
    token = _SCOPE.set((values, counts) if enabled else None)

    def snapshot():
        return dict(version=VERSION, enabled=enabled, **counts,
                    entries=len(values), maximumEntries=MAX_ENTRIES,
                    maximumRetainedBytes=MAX_BYTES,
                    sharedStrings=len(values.strings),
                    sharedStringBytes=sum(row[2] for row in values.strings.values()),
                    sharedStringReferences=sum(row[1] for row in values.strings.values()),
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
    # Additional conservative 1,536 bytes cover the bounded root-key tuple,
    # bucket/list references and index bookkeeping (at most 32 short keys).
    # Strings and frozen trees are referenced, not duplicated by the index.
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
