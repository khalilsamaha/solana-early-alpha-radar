"""Bounded diagnostics for the read-only readiness collector; never raw errors."""
import os
import re
import selectors
import signal
import subprocess
import time

import intake as i
from check_intake import ERRORS as CONTEXT_ERRORS

COMMAND_SECONDS = 4
OUTPUT_BYTES = 16384
DIAGNOSTIC_BYTES = 4096
TEMPLATE_FIELDS = ('Id', 'Image', 'State', 'StartedAt', 'Config', 'Cmd', 'Entrypoint',
                   'Env', 'WorkingDir', 'HostConfig', 'PortBindings', 'Tmpfs',
                   'CapDrop', 'CapAdd', 'SecurityOpt', 'StopSignal', 'StopTimeout',
                   'Mounts', 'Labels')
ERRORS = CONTEXT_ERRORS | {
    'readiness-configuration-shape', 'readiness-configuration-identity',
    'readiness-environment-bound', 'readiness-environment-shape',
    'readiness-environment-name', 'readiness-mounts', 'readiness-container-census',
    'readiness-configuration-changed', 'readiness-target-changed',
    'readiness-process-changed', 'readiness-source-changed',
    'docker-template-unavailable', 'docker-permission-denied',
    'docker-diagnostic-limit', 'docker-target-unavailable',
} | {'docker-template-field-unavailable-' + name for name in TEMPLATE_FIELDS}
STAGES = (
    'source-before', 'local-docker-path', 'configuration-before', 'census-before',
    'context-and-process', 'dotenv-metadata', 'proposed-storage', 'data-mount-storage',
    'configuration-after', 'census-after', 'configuration-consistency',
    'target-consistency', 'process-consistency', 'source-after',
)


def code(exc):
    # Do not call __str__: even an exception's message can contain credentials.
    if isinstance(exc, (ValueError, i.host.ReviewError)) and len(exc.args) == 1:
        value = exc.args[0]
        if type(value) is str and value in ERRORS:
            return value
    for cls, label in ((PermissionError, 'permission-denied'),
                       (FileNotFoundError, 'path-unavailable'),
                       (TimeoutError, 'timeout'), (UnicodeError, 'encoding-invalid'),
                       (KeyError, 'required-field-unavailable'),
                       (TypeError, 'type-invalid'), (ValueError, 'value-invalid')):
        if isinstance(exc, cls):
            return label
    return 'observation-unavailable'


def site(exc):
    # Only source-owned filenames and line numbers, never frame locals or paths.
    allowed = {str((i.REPO / name).resolve()): name for name in (
        'r1-production-review/readiness.py', 'r1-production-review/readiness_diagnostics.py',
        'r1-production-review/intake.py', 'r1-host-review/check.py')}
    result = None
    tb = exc.__traceback__
    while tb is not None:
        name = allowed.get(tb.tb_frame.f_code.co_filename)
        if name:
            result = {'source': name, 'line': tb.tb_lineno}
        tb = tb.tb_next
    return result


class Trace:
    def __init__(self):
        self.rows = [{'stage': name, 'status': 'not-run'} for name in STAGES]
        self.failure = None

    def run(self, name, function, *args):
        row = self.rows[STAGES.index(name)]
        if row['status'] != 'not-run' or self.failure is not None:
            raise ValueError('diagnostic-stage-reuse')
        row.update(status='started', started_utc=i.stamp())
        clock = time.monotonic()
        try:
            result = function(*args)
        except Exception as exc:
            row['status'] = 'unavailable'
            self.failure = {'stage': name, 'code': code(exc), 'site': site(exc)}
            raise
        else:
            row['status'] = 'completed'
            return result
        finally:
            row['finished_utc'] = i.stamp()
            row['elapsed_seconds'] = round(time.monotonic() - clock, 6)


def stderr_code(data):
    # Constant classifications only. A match describes the CLI diagnostic, not
    # a verified root cause. Neither stderr nor substrings leave this function.
    value = data.lower()
    if b'template parsing error' in value or b'template execution error' in value:
        match = re.search(rb'(?:map has no entry for key "([A-Za-z]+)"|'
                          rb"can't evaluate field ([A-Za-z]+) in type)", data)
        if match:
            field = next(value for value in match.groups() if value is not None)
            for known in TEMPLATE_FIELDS:
                if field == known.encode('ascii'):
                    return 'docker-template-field-unavailable-' + known
        return 'docker-template-unavailable'
    if b'permission denied' in value:
        return 'docker-permission-denied'
    if b'no such container' in value or b'no such object' in value:
        return 'docker-target-unavailable'
    return 'docker-inspect-unavailable'


def command(config, *args):
    """Same fixed local Docker requests/bounds, plus bounded in-memory stderr.

    This entry is deliberately limited to the two readiness request shapes.
    Context/identity observation continues to use its accepted collector.
    """
    inspect = (len(args) == 6 and args[:4] == ('inspect', '--type', 'container', '--format')
               and args[-1] == i.host.TARGET)
    census = args == ('ps', '--no-trunc', '--format', '{{.ID}}')
    if not (inspect or census):
        raise ValueError('readiness-command-not-allowed')
    process = subprocess.Popen(
        [i.host.DOCKER, '--config', str(config), '--host', 'unix://' + i.host.SOCKET, *args],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=i.host.ENV, start_new_session=True)
    buffers = {'stdout': bytearray(), 'stderr': bytearray()}
    deadline = time.monotonic() + COMMAND_SECONDS
    try:
        with selectors.DefaultSelector() as selector:
            for stream, name in ((process.stdout, 'stdout'), (process.stderr, 'stderr')):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise i.host.ReviewError('docker-timeout')
                events = selector.select(remaining)
                if not events:
                    raise i.host.ReviewError('docker-timeout')
                for key, _ in events:
                    raw = os.read(key.fileobj.fileno(), 4096)
                    if not raw:
                        selector.unregister(key.fileobj)
                        continue
                    buffers[key.data].extend(raw)
                    limit = OUTPUT_BYTES if key.data == 'stdout' else DIAGNOSTIC_BYTES
                    if len(buffers[key.data]) > limit:
                        raise i.host.ReviewError('docker-output-limit' if key.data == 'stdout'
                                                 else 'docker-diagnostic-limit')
        try:
            process.wait(timeout=max(0.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise i.host.ReviewError('docker-timeout') from None
        if process.returncode:
            raise i.host.ReviewError(stderr_code(buffers['stderr']))
        return bytes(buffers['stdout'])
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=1)
        process.stdout.close()
        process.stderr.close()
