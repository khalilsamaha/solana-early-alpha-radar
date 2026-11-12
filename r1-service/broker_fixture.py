"""Command-driven offline broker process. No live transport or credential input."""
import os
from pathlib import Path
import signal
import sys
import integrated_common as common


def bootstrap(parent):
    # Separate integration profile: waits for Docker, unlike the 10s runtime unit fixture.
    import ctypes
    import resource
    import socket
    if sys.platform != 'linux' or parent <= 1:
        raise RuntimeError('service-platform')
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != parent:
        raise RuntimeError('service-parent')
    os.umask(0o077)
    for key, value in ((resource.RLIMIT_CORE, 0), (resource.RLIMIT_AS, 256*1024**2),
                       (resource.RLIMIT_CPU, 10), (resource.RLIMIT_FSIZE, 44*1024**2), (resource.RLIMIT_NOFILE, 32)):
        resource.setrlimit(key, (value, value))
        if resource.getrlimit(key) != (value, value): raise RuntimeError('service-resource')
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.setitimer(signal.ITIMER_REAL, 45)
    def guard(event, args):
        if (event in {'subprocess.Popen','os.fork','os.forkpty','os.posix_spawn','os.exec',
                     'socket.getaddrinfo','socket.gethostbyname','socket.gethostbyaddr','socket.getnameinfo'}
                or event == 'socket.__new__' and args[1] in (socket.AF_INET, socket.AF_INET6)
                or event in {'socket.connect','socket.sendto'} and args[0].family in (socket.AF_INET, socket.AF_INET6)):
            raise RuntimeError('service-offline-forbidden')
    sys.addaudithook(guard)


def run(directory, ipc, parent, fd, scenario, pipe_fd):
    bootstrap(parent)
    import asyncio
    import re
    import threading
    import credential
    from capture import Capture, CaptureError, Limits, canonical, digest, exclusive_file, strict_json
    from handoff import path_without_links, read_private
    from measurement import Journal
    from provider_wire import Wire, secret_variants
    from session_bundle import export_session, restore_session
    from shared_owner import Owner
    from shared_discovery import Server, deliver
    import shared_session
    if (dict(os.environ) != common.ENVIRONMENT or not sys.flags.ignore_environment
            or not sys.flags.no_user_site or not sys.dont_write_bytecode
            or scenario not in ('normal','cleanup-failure') or pipe_fd not in (-1,) and pipe_fd < 3):
        raise CaptureError('service-environment')
    directory, ipc = path_without_links(directory), path_without_links(ipc)
    raw = read_private(directory/'manifest.json', 65536)
    expected = {'schema_version':1, 'mode':'offline-service-integration', 'parent_pid':parent,
                'scenario':scenario, 'transport':'pipe' if pipe_fd >= 3 else 'unix',
                'source_sha256':common.pins(), 'resources':common.RESOURCES}
    if strict_json(raw) != expected: raise CaptureError('service-manifest')
    secret = credential.consume(fd)
    if not re.fullmatch(r'R1-SYNTHETIC-[0-9a-f]{32}', secret):
        raise CaptureError('service-synthetic-required')
    variants = secret_variants(secret)

    async def exercise():
        class Connection:
            def __init__(self):
                self.frames=asyncio.Queue(); self.closed=False; self.sent=[]; self.transport=self
            def abort(self): self.closed=True
            async def wait_closed(self): pass
            async def send(self, command):
                row=strict_json(command.encode()); self.sent.append(row)
                if row['method']=='subscribeTokenTrade':
                    for kind in ('buy','sell','migration'): self.frames.put_nowait(event(kind))
                if scenario=='cleanup-failure' and row['method']=='unsubscribeTokenTrade':
                    raise RuntimeError(secret)
            async def recv_streaming(self, decode=False):
                yield await self.frames.get()
        def event(kind, mint='1'*31+'2'):
            return canonical({'txType':kind,'mint':mint,'signature':'2'*88,'initialBuy':0}).encode()
        def reply(event_name, **values):
            print(canonical({'event':event_name, **values}), flush=True)
        connection=Connection(); wire=Wire(connection, variants)
        async def factory(): return wire
        owner=Owner(factory); server=Server(owner, ipc) if pipe_fd == -1 else None
        loop=asyncio.get_running_loop()
        reader=asyncio.StreamReader(limit=128)
        input_transport=write_transport=worker=delivery=None
        output_file=None; progress={'frames_sent':0}
        try:
            input_transport,_=await loop.connect_read_pipe(lambda:asyncio.StreamReaderProtocol(reader),sys.stdin.buffer)
            if server:
                await server.start(); progress=server.progress
            else:
                output_file=os.fdopen(pipe_fd,'wb',buffering=0)
                write_transport,protocol=await loop.connect_write_pipe(lambda:asyncio.streams.FlowControlMixin(loop=loop),output_file)
                writer=asyncio.StreamWriter(write_transport,protocol,None,loop)
                delivery=asyncio.create_task(deliver(owner,writer,progress))
            reply('bound', upstream_attempts=0, credential_descriptor_closed=True)
            for command in ('peer','start','retire','stop'):
                if await asyncio.wait_for(reader.readline(),15) != (command+'\n').encode():
                    raise CaptureError('service-command-order')
                if command=='peer':
                    if server: await asyncio.wait_for(server.connected.wait(),3)
                    reply('peer', peer_uid_verified=server is not None, upstream_attempts=0)
                elif command=='start':
                    await owner.start(); lease=owner.attach(5); ready=threading.Event()
                    def capture_thread():
                        with Journal(directory/'session.jsonl') as journal:
                            with Capture(directory/'capture',Limits(messages=4,seconds=5,sample_modulus=1)) as capture:
                                ready.set()
                                return asyncio.run(shared_session.run(capture,lease,journal))
                    worker=asyncio.create_task(asyncio.to_thread(capture_thread))
                    async with asyncio.timeout(3):
                        while not ready.is_set(): await asyncio.sleep(0.002)
                    connection.frames.put_nowait(event('create'))
                    reply('started', upstream_attempts=owner.receipt()['upstream_attempts'])
                elif command=='retire':
                    result=await asyncio.wait_for(asyncio.shield(worker),7)
                    if result['outcome'] != ('capture-stopped' if scenario=='normal' else 'transport-cleanup-failed'):
                        raise CaptureError('service-research-result')
                    if scenario=='normal':
                        if owner.closed: raise CaptureError('service-premature-close')
                        connection.frames.put_nowait(event('create','1'*31+'3'))
                    async with asyncio.timeout(1):
                        while progress['frames_sent'] != (3 if scenario=='normal' else 2): await asyncio.sleep(0.002)
                    reply('retired', cleanup=owner.receipt()['cleanup']['outcome'], admission_closed=not lease.active)
                else:
                    await owner.close()
                    if server: await server.close()
                    if delivery:
                        delivery.cancel(); await asyncio.gather(delivery,return_exceptions=True)
                    if write_transport: write_transport.close()
                    if not connection.closed or len(connection.sent)!=4:
                        raise CaptureError('service-close-evidence')
                    reply('closed', connection_closed=True)
            return {'research':result,'owner':owner.receipt(),'discovery_frames':progress['frames_sent'],
                    'peer_uid_verified':server is not None, 'wire_credential_redaction_enabled':True}
        finally:
            await owner.close()
            if server: await server.close()
            if delivery:
                delivery.cancel(); await asyncio.gather(delivery,return_exceptions=True)
            if write_transport: write_transport.close()
            if input_transport: input_transport.close()
            if worker and not worker.done():
                await asyncio.wait_for(asyncio.shield(worker),2)

    result=asyncio.run(exercise())
    exported=export_session(directory/'capture',directory/'session.jsonl',directory/'export')
    restored=restore_session(directory/'export/session.zip',exported['bundle_sha256'],directory/'restore')
    if exported['capture']!=restored['capture'] or exported['measurement']!=restored['measurement']:
        raise CaptureError('service-session-replay')
    receipt={'schema_version':1,'manifest_sha256':digest(raw),'shared':result,
             'session_bundle_sha256':exported['bundle_sha256'],'session_bundle_bytes':exported['bundle_bytes'],
             'capture':restored['capture'],'measurement':restored['measurement'],
             'credential_descriptor_closed':True,'complete_session_replayed':True,
             'provider_connection_opened':False,'real_credential_used':False,
             'internet_and_dns_blocked':True,'child_process_creation_blocked':True,
             'parent_death_sigkill':True,'resources':common.RESOURCES}
    exclusive_file(directory/'worker-result.json',(canonical(receipt)+'\n').encode())
    for path in directory.rglob('*'):
        if path.is_file() and any(v in path.read_bytes() for v in variants):
            raise CaptureError('service-secret-in-output')


if __name__=='__main__':
    try:
        if len(sys.argv)!=7: raise RuntimeError('service-arguments')
        run(sys.argv[1],sys.argv[2],int(sys.argv[3]),int(sys.argv[4]),sys.argv[5],int(sys.argv[6]))
    except BaseException:
        sys.exit(1)
