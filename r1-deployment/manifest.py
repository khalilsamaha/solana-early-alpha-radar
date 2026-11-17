"""Immutable production planning inputs. No launcher, observation or approval API."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 65536
HEX = re.compile(r'[a-f0-9]{64}')
POLICY = {'research_seconds', 'service_seconds', 'setup_seconds', 'shutdown_seconds',
          'memory_bytes', 'cpu_seconds', 'open_files', 'raw_bytes', 'database_bytes',
          'journal_bytes', 'receipt_bytes', 'retained_runs', 'quarantined_runs',
          'headroom_bytes', 'retention_seconds', 'funding_lamports',
          'data_fee_lamports', 'exposed_lamports', 'remaining_engineering_minutes'}
CONFIG = {'scanner_image', 'scanner_config_sha256', 'rollback_config_sha256',
          'shared_scanner_image', 'shared_scanner_manifest_sha256',
          'owner_source_sha256', 'registry_path', 'endpoint_path', 'capture_path',
          'remote_destination_sha256', 'credential_method'}


def check(condition, code):
    if not condition:
        raise ValueError(code)


def raw(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def parse(data):
    def pairs(items):
        result = {}
        for k, v in items:
            check(k not in result, 'duplicate-key')
            result[k] = v
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda _: check(False, 'json-constant'))


def sources():
    names = ['r1-deployment/manifest.py', 'r1-deployment/test_manifest.py',
             'r1-deployment/README.md', 'r1-integration/profile.py',
             'r1-integration/separated_session.py', 'r1-integration/envelope.py',
             'r1-native-handoff/native.py', 'r1-native-handoff/consumer.mjs',
             'r1-handoff/coordinator.py', 'r1-control/control.py']
    return {n: digest((ROOT/n).read_bytes()) for n in names}


def absolute(value):
    check(isinstance(value, str) and value.startswith('/') and
          str(Path(value)) == value and '..' not in Path(value).parts and
          not any(ord(c) < 32 for c in value), 'path')
    return Path(value)


def validate(config, policy):
    check(type(config) is dict and set(config) == CONFIG, 'config-fields')
    check(type(policy) is dict and set(policy) == POLICY, 'policy-fields')
    for key, value in config.items():
        if value is None:
            continue
        if key.endswith('_sha256'):
            check(isinstance(value, str) and HEX.fullmatch(value), 'config-hash')
        elif key in ('scanner_image','shared_scanner_image'):
            check(isinstance(value, str) and value.startswith('sha256:') and
                  HEX.fullmatch(value[7:]), 'image-digest')
        elif key.endswith('_path'):
            absolute(value)
        else:
            check(value == 'sealed-fd', 'credential-method')
    registry, endpoint, capture = (config[k] for k in ('registry_path', 'endpoint_path', 'capture_path'))
    if registry and endpoint:
        check(Path(endpoint).parent == Path(registry) and Path(endpoint).name == 'discovery.sock', 'endpoint-binding')
    if registry and capture:
        a, b = Path(registry), Path(capture)
        check(a != b and a not in b.parents and b not in a.parents, 'path-overlap')
    for key, value in policy.items():
        if value is None:
            continue
        check(type(value) is int and 0 <= value <= 2**53-1, 'policy-integer')
        if key not in ('funding_lamports', 'data_fee_lamports', 'exposed_lamports'):
            check(value > 0, 'policy-positive')
    for key in ('research_seconds', 'service_seconds'):
        check(policy[key] is None or policy[key] <= 172800, 'draft-duration-ceiling')
    for key in ('setup_seconds', 'shutdown_seconds'):
        check(policy[key] is None or policy[key] <= 30, 'shutdown-setup-ceiling')
    if policy['research_seconds'] is not None and policy['service_seconds'] is not None:
        check(policy['research_seconds'] <= policy['service_seconds'], 'service-lifetime')
    check(policy['raw_bytes'] is None or policy['raw_bytes'] <= 8*1024**2, 'draft-raw-ceiling')


def capacity(policy):
    """Conservative bytes on ONE filesystem; no allocation/retention claim."""
    keys = ('raw_bytes', 'database_bytes', 'journal_bytes', 'receipt_bytes',
            'retained_runs', 'quarantined_runs', 'headroom_bytes')
    if any(policy[k] is None for k in keys):
        return None
    # Original DB plus worst-case rollback copy, raw data, journal and receipts.
    source = policy['raw_bytes'] + 2*policy['database_bytes'] + 4096 + policy['journal_bytes'] + policy['receipt_bytes']
    # ZIP metadata allowance is a proposed bound; exporter validation remains open.
    envelope = source + 65536
    retained = (policy['retained_runs'] + policy['quarantined_runs']) * (source + envelope)
    # One new capture, export, upload staging, download staging and isolated restore.
    active = 2*source + 3*envelope
    required = retained + active + policy['headroom_bytes']
    check(required <= 2**63-1, 'capacity-overflow')
    return {'source_max_bytes': source, 'envelope_max_bytes': envelope,
            'retained_max_bytes': retained, 'active_max_bytes': active,
            'required_free_bytes': required, 'filesystem_scope': 'capture-and-all-staging',
            'space_reserved': False, 'retention_verified': False}


def build(config, policy):
    validate(config, policy)
    config, policy = dict(config), dict(policy)
    blockers = ['missing:'+k for k, v in sorted({**config, **policy}.items()) if v is None]
    blockers += ['production-adapters-unaccepted', 'host-wide-ownership-unverified',
                 'live-profile-unaccepted', 'credential-provisioning-unaccepted',
                 'capacity-and-retention-unverified', 'real-delivery-unaccepted',
                 'exact-pilot-and-rollout-approval-required']
    return {'schema': 1, 'kind': 'r1-production-planning-manifest',
            'config': config, 'policy': policy, 'source_sha256': sources(),
            'capacity': capacity(policy), 'blockers': blockers,
            'activation_authorized': False, 'automatic_resume_allowed': False}


def private_parent(path):
    path = absolute(str(path))
    check(all(not p.is_symlink() for p in (path, *path.parents)), 'path-link')
    s = path.stat()
    check(stat.S_ISDIR(s.st_mode) and s.st_uid == os.getuid() and not s.st_mode & 0o077, 'private-directory')
    return path


def freeze(directory, manifest):
    """Consume a new directory; failures stay retained and cannot be retried."""
    check(raw(manifest) == raw(build(manifest['config'], manifest['policy'])), 'manifest-binding')
    data = raw(manifest); check(len(data) <= MAX_BYTES, 'manifest-size')
    directory = absolute(str(directory)); private_parent(directory.parent)
    directory.mkdir(mode=0o700)
    parent = os.open(directory.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
    fd = os.open(directory/'manifest.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        check(os.write(fd, data) == len(data), 'short-write')
        os.fsync(fd)
    finally:
        os.close(fd)
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return digest(data)


def inspect(directory, expected_sha256):
    """External digest is required. Never observes a host or grants authority."""
    check(isinstance(expected_sha256, str) and HEX.fullmatch(expected_sha256), 'expected-digest')
    directory = private_parent(Path(directory))
    fd = os.open(directory/'manifest.json', os.O_RDONLY | os.O_NOFOLLOW)
    try:
        s = os.fstat(fd)
        check(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_uid == os.getuid() and
              not s.st_mode & 0o077 and s.st_size <= MAX_BYTES, 'private-manifest')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(MAX_BYTES+1)
        check(len(data) <= MAX_BYTES and digest(data) == expected_sha256, 'manifest-digest')
    finally:
        os.close(fd)
    row = parse(data)
    check(raw(row) == data and raw(row) == raw(build(row['config'], row['policy'])), 'manifest-binding')
    return row
