"""Read-only, manifest-bound storage preparation. No allocator or live launcher."""
from datetime import datetime, timezone
import os
from pathlib import Path
import stat
import time
import manifest as m

ROLES = ('capture', 'export', 'upload', 'download', 'restore', 'quarantine')


def pins():
    return {name: m.digest((m.ROOT/name).read_bytes()) for name in
            ('r1-deployment/storage.py', 'r1-deployment/test_storage.py',
             'r1-deployment/STORAGE.md')}


def open_directory(path):
    """Traverse every component without following links; caller owns returned FD."""
    path = m.absolute(str(path))
    m.check(1 <= len(path.parts)-1 <= 64, 'storage-path-depth')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open('/', flags)
    try:
        for component in path.parts[1:]:
            next_fd = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        row = os.fstat(fd)
        m.check(row.st_uid == os.getuid() and not row.st_mode & 0o077, 'storage-private-directory')
        result, fd = fd, None
        return result
    finally:
        if fd is not None:
            os.close(fd)


def metadata(fd):
    identity = os.fstat(fd)
    m.check(stat.S_ISDIR(identity.st_mode) and identity.st_uid == os.getuid() and
            not identity.st_mode & 0o077, 'storage-directory-changed')
    return {'device': identity.st_dev, 'inode': identity.st_ino,
            'uid': identity.st_uid, 'mode': stat.S_IMODE(identity.st_mode)}


def sample(fd):
    row = metadata(fd)
    space = os.fstatvfs(fd)
    m.check(not space.f_flag & os.ST_RDONLY, 'storage-readonly-filesystem')
    m.check(space.f_frsize > 0 and space.f_bavail >= 0, 'storage-space-invalid')
    return {**row, 'available_bytes': space.f_bavail * space.f_frsize}


def identity(row):
    return {k: v for k, v in row.items() if k != 'available_bytes'}


def validate_paths(paths, manifest):
    m.check(type(paths) is dict and set(paths) == set(ROLES), 'storage-roles')
    normalized = {k: m.absolute(v) for k, v in paths.items()}
    m.check(manifest['capacity'] is not None and manifest['config']['capture_path'] is not None,
            'storage-budget-missing')
    m.check(str(normalized['capture']) == manifest['config']['capture_path'], 'storage-capture-binding')
    selected = list(normalized.values())
    registry = manifest['config']['registry_path']
    if registry is not None:
        selected.append(m.absolute(registry))
    for i, path in enumerate(selected):
        for other in selected[i+1:]:
            m.check(path != other and path not in other.parents and other not in path.parents,
                    'storage-path-overlap')
    return normalized


def observe(manifest_directory, expected_manifest_sha256, paths):
    """Two bounded samples of six explicit existing directories; no recursive scan.

    Retain the returned report as historical evidence only. The caller must repeat
    admission checks immediately before a separately authorized mutation. Paths
    are a caller proposal bound into this report, not independently approved.
    """
    started = datetime.now(timezone.utc).isoformat()
    start_clock = time.monotonic()
    manifest = m.inspect(manifest_directory, expected_manifest_sha256)
    paths = validate_paths(paths, manifest)
    before_pins = pins()
    fds = {}
    try:
        for role in ROLES:
            fds[role] = open_directory(paths[role])
        before = {k: sample(fd) for k, fd in fds.items()}
        m.check(len({v['device'] for v in before.values()}) == 1, 'storage-multiple-filesystems')
        m.check(len({(v['device'], v['inode']) for v in before.values()}) == len(ROLES), 'storage-directory-alias')
        after = {}
        for role in ROLES:
            # Reopen through the namespace to detect a path replacement, not just
            # query the original (possibly unlinked) open descriptor again.
            fd = open_directory(paths[role])
            try:
                after[role] = sample(fd)
            finally:
                os.close(fd)
            m.check(identity(before[role]) == identity(after[role]), 'storage-path-replaced')
            m.check(identity(before[role]) == metadata(fds[role]), 'storage-held-directory-changed')
        m.check(pins() == before_pins and
                m.inspect(manifest_directory, expected_manifest_sha256) == manifest, 'storage-source-or-manifest-changed')
        elapsed = time.monotonic() - start_clock
        m.check(elapsed >= 0, 'storage-clock-regressed')
        available = min(v['available_bytes'] for batch in (before, after) for v in batch.values())
        required = manifest['capacity']['required_free_bytes']
        return {'schema': 1, 'kind': 'r1-storage-observation',
                'manifest_sha256': expected_manifest_sha256, 'source_sha256': before_pins,
                'paths': {k: str(v) for k, v in paths.items()}, 'before': before, 'after': after,
                'started_utc': started, 'finished_utc': datetime.now(timezone.utc).isoformat(),
                'elapsed_seconds': elapsed, 'available_bytes': available, 'required_bytes': required,
                'status': 'storage-observed-activation-blocked' if available >= required else 'storage-insufficient-activation-blocked',
                'capacity_sample_sufficient': available >= required,
                'remaining_blockers': list(manifest['blockers']),
                'space_reserved': False, 'retention_verified': False, 'writes_performed': False,
                'activation_authorized': False, 'automatic_resume_allowed': False}
    finally:
        for fd in fds.values():
            os.close(fd)
