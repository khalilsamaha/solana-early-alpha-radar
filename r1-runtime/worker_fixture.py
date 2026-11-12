"""Fixed offline worker. Reads a synthetic sealed descriptor; has no live branch."""
import os
from pathlib import Path
import signal
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent/'r1-data'))


def run(directory, parent, fd, scenario):
    from supervisor_worker import bootstrap
    bootstrap(parent)  # parent-death kill, resource limits, no Internet/DNS/children
    import asyncio
    import threading
    import boundary
    import credential
    from capture import Capture, CaptureError, Limits, canonical, digest, exclusive_file
    from handoff import read_private, path_without_links
    from measurement import Journal
    from provider_wire import Wire, secret_variants
    from session_bundle import export_session, restore_session
    from shared_owner import Owner
    import shared_session

    if (dict(os.environ) != boundary.ENVIRONMENT or not sys.flags.ignore_environment
            or not sys.flags.no_user_site or not sys.dont_write_bytecode or scenario not in boundary.SCENARIOS):
        raise CaptureError('runtime-environment')
    directory = path_without_links(directory)
    manifest_raw = read_private(directory/'attempt.json', 65536)
    from capture import strict_json
    expected = {'schema_version':1, 'mode':'offline-runtime', 'scenario':scenario,
                'parent_pid':parent, 'source_sha256':boundary.pins()}
    if strict_json(manifest_raw) != expected:
        raise CaptureError('runtime-manifest')
    value = credential.consume(fd)
    # Rehearsal accepts only its generated sentinel, never a real provider key.
    if not value.startswith('R1-SYNTHETIC-') or len(value) != 45:
        raise CaptureError('runtime-synthetic-required')
    variants = secret_variants(value)
    if scenario == 'stall':
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    exclusive_file(directory/'ready.json',b'{"credential_descriptor_closed":true}\n')
    if scenario == 'credential-echo':
        # Deliberately tainted diagnostics; supervisor must discard both streams.
        print(value, flush=True); print(value, file=sys.stderr, flush=True)
        raise RuntimeError(value)
    if scenario == 'stall':
        while True: signal.pause()

    async def exercise():
        class Connection:
            def __init__(self):
                self.frames = asyncio.Queue()
                self.closed = False
                self.transport = self
                self.sent = []
            def abort(self): self.closed = True
            async def wait_closed(self): pass
            async def send(self, raw):
                row = strict_json(raw.encode()); self.sent.append(row)
                if row['method']=='subscribeTokenTrade':
                    for kind in ('buy','sell','migration'): self.frames.put_nowait(event(kind))
                if scenario=='cleanup-failure' and row['method']=='unsubscribeTokenTrade':
                    raise RuntimeError(value)
            async def recv_streaming(self, decode=False):
                yield await self.frames.get()
        def event(kind, mint='1'*31+'2'):
            return canonical({'txType':kind,'mint':mint,'signature':'2'*88,'initialBuy':0}).encode()
        connection=Connection()
        wire=Wire(connection, variants)
        async def factory(): return wire
        owner=Owner(factory)
        discovery=[]
        async def drain():
            try:
                while True: discovery.append(await owner.discovery.recv())
            except CaptureError: pass
        worker = consumer = None
        try:
            await owner.start()
            lease=owner.attach(5)
            consumer=asyncio.create_task(drain())
            ready=threading.Event()
            def capture_thread():
                with Journal(directory/'session.jsonl') as journal:
                    with Capture(directory/'capture',Limits(messages=4,seconds=5,sample_modulus=1)) as capture:
                        ready.set()
                        return asyncio.run(shared_session.run(capture,lease,journal))
            worker=asyncio.create_task(asyncio.to_thread(capture_thread))
            async with asyncio.timeout(3):
                while not ready.is_set(): await asyncio.sleep(0.002)
            connection.frames.put_nowait(event('create'))
            result=await asyncio.wait_for(asyncio.shield(worker),7)
            if scenario=='normal':
                if owner.closed: raise CaptureError('runtime-discovery-ended')
                connection.frames.put_nowait(event('create','1'*31+'3'))
                async with asyncio.timeout(1):
                    while len(discovery)!=3: await asyncio.sleep(0.002)
            await owner.close()
            await consumer
            expected_outcome='capture-stopped' if scenario=='normal' else 'transport-cleanup-failed'
            if result['outcome']!=expected_outcome or not connection.closed or len(connection.sent)!=4:
                raise CaptureError('runtime-shared-expectation')
            return {'research':result,'owner':owner.receipt(),'discovery_frames':len(discovery),
                    'wire_credential_redaction_enabled':True}
        finally:
            await owner.close()
            if consumer:
                consumer.cancel(); await asyncio.gather(consumer,return_exceptions=True)
            if worker and not worker.done():
                await asyncio.wait_for(asyncio.shield(worker),2)

    result=asyncio.run(exercise())
    exported=export_session(directory/'capture',directory/'session.jsonl',directory/'export')
    restored=restore_session(directory/'export/session.zip',exported['bundle_sha256'],directory/'restore')
    if exported['capture']!=restored['capture'] or exported['measurement']!=restored['measurement']:
        raise CaptureError('runtime-replay')
    receipt={'schema_version':1,'manifest_sha256':digest(manifest_raw),'shared':result,
        'session_bundle_sha256':exported['bundle_sha256'],'session_bundle_bytes':exported['bundle_bytes'],
        'capture':restored['capture'],'measurement':restored['measurement'],
        'credential_descriptor_closed':True,'complete_session_replayed':True,
        'internet_and_dns_blocked':True,'child_process_creation_blocked':True,
        'parent_death_sigkill':True,'core_dump_limit_zero':True,'real_credential_used':False,
        'provider_connection_opened':False}
    exclusive_file(directory/'worker-result.json',(canonical(receipt)+'\n').encode())
    # Scan all persisted worker output against plaintext and encoded sentinel.
    for path in directory.rglob('*'):
        if path.is_file() and any(v in path.read_bytes() for v in variants):
            raise CaptureError('runtime-credential-in-output')


if __name__=='__main__':
    try:
        if len(sys.argv)!=5: raise RuntimeError('runtime-arguments')
        run(sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),sys.argv[4])
    except BaseException:
        sys.exit(1)
