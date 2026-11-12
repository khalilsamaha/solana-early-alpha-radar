"""Disposable network-disabled scanner consumer. Never controls production containers."""
import asyncio
import importlib.util
import os
from pathlib import Path
import re
import uuid

from capture import CaptureError, digest, exclusive_file, strict_json
from handoff import path_without_links

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
spec = importlib.util.spec_from_file_location('r1_host_identity', REPO / 'r1-host-review/check.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
IMAGE = 'sha256:786529348e5b7b6563a33d8c358c3d03c97110879d6ad53af0fbae65cd0249f9'
LABEL = 'org.solana-radar.r1-rehearsal'
CODE_FILES = ('r1-data/shared_scanner_fixture.mjs', 'scanner/package.json',
    'scanner/src/core/launch-registry.js', 'scanner/src/adapters/pumpportal-source.js',
    'scanner/src/adapters/pumpportal.js', 'scanner/src/adapters/pumpportal-shared.js',
    'scanner/src/adapters/pumpportal-events.js')
FORMAT = ('{"id":{{json .Id}},"image":{{json .Image}},'
    '"label":{{json (index .Config.Labels "org.solana-radar.r1-rehearsal")}},'
    '"user":{{json .Config.User}},"network":{{json .HostConfig.NetworkMode}},'
    '"readonly":{{json .HostConfig.ReadonlyRootfs}},"privileged":{{json .HostConfig.Privileged}},'
    '"restart":{{json .HostConfig.RestartPolicy.Name}},"mounts":{{json .Mounts}},'
    '"running":{{json .State.Running}},"exit_code":{{json .State.ExitCode}},'
    '"memory":{{json .HostConfig.Memory}},"pids":{{json .HostConfig.PidsLimit}},'
    '"swap":{{json .HostConfig.MemorySwap}},"cpus":{{json .HostConfig.NanoCpus}},'
    '"init":{{json .HostConfig.Init}},"logging":{{json .HostConfig.LogConfig.Type}},'
    '"caps":{{json .HostConfig.CapDrop}},"security":{{json .HostConfig.SecurityOpt}}}')


def safe_directory(value):
    p = path_without_links(value)
    if any(x in str(p) for x in (',', '\n', '\r', '\x00')):
        raise CaptureError('container-mount-path')
    st = p.lstat()
    if not p.is_dir() or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise CaptureError('container-private-directory')
    return p


def stage(directory):
    directory.mkdir(mode=0o700)
    for name in CODE_FILES:
        source = REPO / name
        if source.is_symlink() or not source.is_file():
            raise CaptureError('container-source')
        target = directory / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        exclusive_file(target, source.read_bytes())
    return {n: digest((directory / n).read_bytes()) for n in CODE_FILES}


class Consumer:
    def __init__(self, directory):
        # Fresh private evidence directory. Never accepts a container/image CLI argument.
        self.directory = safe_directory(directory)
        self.config = self.directory / 'empty-docker-config'
        self.config.mkdir(mode=0o700)
        self.code = self.directory / 'code'
        self.code_pins = stage(self.code)
        self.token = uuid.uuid4().hex
        self.name = 'radar-r1-offline-' + self.token
        self.cid = None
        self.attempted = self.created = self.removed = self.cleanup_attempted = False
        self.socket_directory = None
        self.process = None
        self.exit_code = None
        self.inspected_before_start = False

    def cli(self, *args):
        return [host.DOCKER, '--config', str(self.config), '--host', 'unix://' + host.SOCKET, *args]

    def command(self, *args):
        return host.bounded_command(self.cli(*args))

    def create_args(self, socket_directory):
        self.socket_directory = safe_directory(socket_directory)
        if os.getuid() != 1000 or os.geteuid() != 1000 or os.getgid() != 1000 or os.getegid() != 1000:
            raise CaptureError('container-review-uid-mismatch')
        return ['create', '--name', self.name, '--label', LABEL + '=' + self.token,
            '--pull=never', '--network=none', '--restart=no', '--read-only', '--init',
            '--user=1000:1000', '--cap-drop=ALL', '--security-opt=no-new-privileges:true',
            '--memory=128m', '--memory-swap=128m', '--cpus=1', '--pids-limit=32',
            '--log-driver=none', '--no-healthcheck', '--interactive',
            '--mount', f'type=bind,src={self.code},dst=/r1-code,readonly',
            '--mount', f'type=bind,src={self.socket_directory},dst=/r1-ipc,readonly',
            '--entrypoint=/usr/bin/env', IMAGE,
            '-i', 'PATH=/usr/local/bin:/usr/bin:/bin', 'LANG=C.UTF-8', 'LC_ALL=C.UTF-8',
            'node', '/r1-code/r1-data/shared_scanner_fixture.mjs', 'unix', '/r1-ipc/discovery.sock']

    def identify(self, reference):
        row = strict_json(self.command('inspect', '--type', 'container', '--format', FORMAT, reference))
        if (not isinstance(row, dict) or not re.fullmatch(r'[0-9a-f]{64}', row.get('id', ''))
                or row.get('label') != self.token or row.get('image') != IMAGE
                or self.cid is not None and row['id'] != self.cid):
            raise CaptureError('container-ownership-unconfirmed')
        return row

    def isolation(self, row):
        expected = {'user': '1000:1000', 'network': 'none', 'readonly': True,
            'privileged': False, 'restart': 'no', 'memory': 128 * 1024**2, 'pids': 32,
            'swap': 128 * 1024**2, 'cpus': 1000000000, 'init': True, 'logging': 'none'}
        if any(type(row.get(k)) is not type(v) or row[k] != v for k, v in expected.items()):
            raise CaptureError('container-isolation-unconfirmed')
        if row.get('caps') != ['ALL'] or row.get('security') not in (['no-new-privileges:true'], ['no-new-privileges']):
            raise CaptureError('container-isolation-unconfirmed')
        mounts = row.get('mounts')
        wanted = {'/r1-code': str(self.code), '/r1-ipc': str(self.socket_directory)}
        if not isinstance(mounts, list) or len(mounts) != 2:
            raise CaptureError('container-mounts-unconfirmed')
        for m in mounts:
            if (not isinstance(m, dict) or m.get('Destination') not in wanted
                    or m.get('Source') != wanted.pop(m['Destination'])
                    or m.get('Type') != 'bind' or m.get('RW') is not False):
                raise CaptureError('container-mounts-unconfirmed')
        if wanted:
            raise CaptureError('container-mounts-unconfirmed')

    async def operation(self, function, *args):
        # Wait for a dispatched daemon operation before reconciling on cancellation.
        # Cancelling to_thread alone would leave its create request in flight.
        pending = asyncio.create_task(asyncio.to_thread(function, *args))
        try:
            return await asyncio.shield(pending)
        except asyncio.CancelledError:
            try:
                await pending
            except Exception:
                pass
            raise

    async def start(self, socket_path, ignored_directory):
        if self.attempted:
            raise CaptureError('container-restart-forbidden')
        host.trusted_local_docker()
        args = self.create_args(Path(socket_path).parent)
        self.attempted = True
        # Slow daemon commands run away from the owner's event loop.
        raw = await self.operation(self.command, *args)
        cid = raw.decode('ascii').strip()
        if not re.fullmatch(r'[0-9a-f]{64}', cid):
            raise CaptureError('container-create-unconfirmed')
        self.cid, self.created = cid, True
        row = await self.operation(self.identify, self.cid)
        self.isolation(row)
        if row.get('running') is not False:
            raise CaptureError('container-start-state')
        self.inspected_before_start = True
        self.process = await asyncio.create_subprocess_exec(*self.cli('start', '--attach', '--interactive', self.cid),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, env=host.ENV, limit=8192, start_new_session=True)
        return self.process

    async def cleanup(self):
        if not self.attempted or self.removed:
            return
        if self.cleanup_attempted:
            raise CaptureError('container-cleanup-unconfirmed')
        self.cleanup_attempted = True
        # A timed-out create may have succeeded at the daemon. Reconcile only our
        # random name and matching label/image, never delete an unverified object.
        row = await self.operation(self.identify, self.cid or self.name)
        self.cid, self.created = row['id'], True
        if row.get('running') is False and type(row.get('exit_code')) is int:
            self.exit_code = row['exit_code']
        raw = await self.operation(self.command, 'rm', '--force', '--volumes', self.cid)
        if raw.decode('ascii').strip() != self.cid:
            raise CaptureError('container-removal-unconfirmed')
        # A successful daemon removal response confirms this exact ID was removed;
        # do not infer success from a failing inspect (which could be daemon loss).
        self.removed = True
        if self.process and self.process.returncode is None:
            await asyncio.wait_for(self.process.wait(), 2)
        if any(digest((self.code / n).read_bytes()) != h for n, h in self.code_pins.items()):
            raise CaptureError('container-staged-source-changed')

    def receipt(self):
        return {'name': self.name, 'ownership_label': LABEL + '=' + self.token,
            'image': IMAGE, 'created': self.created, 'removed': self.removed,
            'inspected_before_start': self.inspected_before_start, 'exit_code': self.exit_code,
            'network_requested': 'none', 'mounts_read_only_verified': self.inspected_before_start,
            'user_requested': '1000:1000', 'cleanup_attempted': self.cleanup_attempted,
            'staged_source_sha256': self.code_pins, 'production_container_controlled': False}


async def missing_endpoint(consumer, directory):
    """Starting without the broker endpoint must fail locally, never use direct mode."""
    path = directory / 'discovery.sock'
    child = None
    try:
        child = await consumer.start(path, directory)
        child.stdin.close()
        data = await asyncio.wait_for(child.stdout.read(8193), 5)
        await asyncio.wait_for(child.wait(), 2)
        if len(data) > 8192 or child.returncode != 1:
            raise CaptureError('container-missing-endpoint-expectation')
        row = strict_json(data)
        if row != {'tokens': 0, 'creations': 0, 'discovery_gaps': 0,
                   'sources': [], 'upstream_connections_opened': 0}:
            raise CaptureError('container-missing-endpoint-expectation')
    finally:
        if child and child.returncode is None:
            child.kill()
            await child.wait()
        await consumer.cleanup()
    return {'endpoint_absent_rejected': True, 'synthetic_upstream_attempts': 0,
            'direct_fallback_attempts': 0, 'container': consumer.receipt()}
