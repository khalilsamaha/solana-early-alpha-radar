"""Private-file to sealed anonymous descriptor. Library only; never prints secrets."""
import fcntl
import os
from pathlib import Path
import stat
import sys

from capture import CaptureError
from provider_wire import secret_variants

# Linux UAPI values; some Python builds omit these exported constants.
ADD_SEALS = getattr(fcntl, 'F_ADD_SEALS', 1033)
GET_SEALS = getattr(fcntl, 'F_GET_SEALS', 1034)
SEALS = 1 | 2 | 4 | 8  # SEAL, SHRINK, GROW, WRITE
MAX_BYTES = 4096


def validated(raw):
    if type(raw) is not bytes or not 16 <= len(raw) <= MAX_BYTES:
        raise CaptureError('credential-invalid')
    try:
        value = raw.decode('ascii')
        secret_variants(value)
        return value
    except Exception:
        raise CaptureError('credential-invalid') from None


def identity(st):
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def read_private(value):
    """Walk open directory descriptors, refusing links and writable ancestors."""
    directory = fd = None
    try:
        if sys.platform != 'linux' or os.getuid() != os.geteuid():
            raise CaptureError('credential-platform')
        path = Path(value)
        if (not path.is_absolute() or str(path) != os.fspath(value)
                or any(p in {'.', '..'} for p in path.parts) or len(path.parts) < 3):
            raise CaptureError('credential-path')
        directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
            os.close(directory); directory = child
            st = os.fstat(directory)
            sticky_root = st.st_uid == 0 and bool(st.st_mode & stat.S_ISVTX)
            if st.st_uid not in {0, os.getuid()} or st.st_mode & 0o022 and not sticky_root:
                raise CaptureError('credential-ancestor')
        parent = os.fstat(directory)
        if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
            raise CaptureError('credential-parent')
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) not in {0o400, 0o600} or not 16 <= before.st_size <= MAX_BYTES):
            raise CaptureError('credential-file')
        raw = os.read(fd, MAX_BYTES + 1)
        after = os.fstat(fd)
        current = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        if identity(before) != identity(after) or identity(after) != identity(current) or len(raw) != before.st_size:
            raise CaptureError('credential-changed')
        validated(raw)
        return raw
    except Exception:
        raise CaptureError('credential-load-refused') from None
    finally:
        if fd is not None: os.close(fd)
        if directory is not None: os.close(directory)


def sealed(raw):
    """Create a CLOEXEC anonymous file; only explicit pass_fds transfers it."""
    validated(raw)
    fd = None
    try:
        if sys.platform != 'linux':
            raise CaptureError('credential-platform')
        fd = os.memfd_create('r1-credential', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        os.fchmod(fd, 0o600)
        if os.write(fd, raw) != len(raw):
            raise CaptureError('credential-short-write')
        fcntl.fcntl(fd, ADD_SEALS, SEALS)
        if fcntl.fcntl(fd, GET_SEALS) & SEALS != SEALS:
            raise CaptureError('credential-seal')
        return fd
    except Exception:
        if fd is not None: os.close(fd)
        raise CaptureError('credential-handoff-refused') from None


def load_descriptor(path):
    return sealed(read_private(path))


def consume(fd):
    """Require immutable anonymous content and close the inherited descriptor."""
    if type(fd) is not int or fd < 3:
        raise CaptureError('credential-descriptor')
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_nlink != 0
                or stat.S_IMODE(st.st_mode) != 0o600 or not 16 <= st.st_size <= MAX_BYTES
                or fcntl.fcntl(fd, GET_SEALS) & SEALS != SEALS):
            raise CaptureError('credential-descriptor')
        return validated(os.pread(fd, MAX_BYTES + 1, 0))
    except Exception:
        raise CaptureError('credential-descriptor-refused') from None
    finally:
        os.close(fd)
