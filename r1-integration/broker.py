"""Isolated worker for the separated session; no live credential/provider arguments."""
import common as c
import os
from pathlib import Path
import sys


STAGE="startup"

def run(directory,ipc,parent,fd,scenario,pipe_fd):
    global STAGE
    import profile
    directory,ipc=map(c.path_without_links,(directory,ipc))
    raw=c.read_private(directory/'manifest.json',65536);manifest=c.strict_json(raw)
    expected={'schema_version':1,'mode':'offline-combined-integration','parent_pid':parent,
              'scenario':scenario,'transport':'pipe' if pipe_fd>=3 else 'unix',
              'source_sha256':c.pins(),'resources':profile.make(15),'request_sha256':manifest.get('request_sha256')}
    if not isinstance(manifest.get('request_sha256'),str) or len(manifest['request_sha256'])!=64 or c.raw(manifest)!=c.raw(expected) or scenario not in ('normal','cleanup-failure'):
        raise c.CaptureError('combined-manifest')
    profile.bootstrap(parent,manifest['resources'])
    import asyncio
    from contextlib import redirect_stderr
    import io
    import re
    import credential
    import separated_session as s
    import fixtures
    from capture import Limits
    from provider_wire import Wire,secret_variants
    from shared_discovery import deliver
    from session_bundle import export_session,restore_session
    from check_session import DIAGNOSTIC
    if (dict(os.environ)!=c.ENVIRONMENT or not sys.flags.ignore_environment
            or not sys.flags.no_user_site or not sys.dont_write_bytecode):
        raise c.CaptureError('combined-environment')
    secret=credential.consume(fd)
    if not re.fullmatch('R1-SYNTHETIC-[0-9a-f]{32}',secret):raise c.CaptureError('combined-sentinel')
    variants=secret_variants(secret)

    async def exercise():
        class Peer(fixtures.Peer):
            async def send(self,command):
                row=c.strict_json(command.encode());self.sent.append(row)
                if row['method']=='subscribeTokenTrade':
                    for kind in ('buy','sell','migration'):self.frames.put_nowait(self.event(kind))
                if row['method']=='unsubscribeTokenTrade' and scenario=='cleanup-failure':
                    raise RuntimeError(secret)
        peer=Peer(scenario,4)
        class PipeServer(fixtures.TestServer):
            async def start(self):
                self.accepted=True;self.connected.set()
                loop=asyncio.get_running_loop()
                self.file=os.fdopen(pipe_fd,'wb',buffering=0)
                class Protocol(asyncio.streams.FlowControlMixin):
                    def __init__(self):
                        super().__init__(loop=loop);self.closed=loop.create_future()
                    def connection_lost(self,exc):
                        super().connection_lost(exc)
                        if not self.closed.done():self.closed.set_result(None)
                    def _get_close_waiter(self,stream):return self.closed
                self.transport,protocol=await loop.connect_write_pipe(Protocol,self.file)
                self.writer=asyncio.StreamWriter(self.transport,protocol,None,loop)
                self.task=asyncio.create_task(deliver(self.owner,self.writer,self.progress))
            async def close(self):
                await super().close();self.writer.close()
                await asyncio.wait_for(self.writer.wait_closed(),1)
        async def factory():
            peer.frames.put_nowait(peer.event('create'))
            return Wire(peer,variants)
        shutdown,retired,bound,peer_ready,started,admitted=(asyncio.Event() for _ in range(6))
        loop=asyncio.get_running_loop();reader=asyncio.StreamReader(limit=128)
        input_transport,_=await loop.connect_read_pipe(lambda:asyncio.StreamReaderProtocol(reader),sys.stdin.buffer)
        if pipe_fd>=3:s.Server=PipeServer
        task=asyncio.create_task(s.run(directory/'control',ipc,factory,Limits(messages=4,seconds=5,sample_modulus=1),
            shutdown=shutdown,research_done=retired,endpoint_ready=bound,peer_ready=peer_ready,upstream_ready=started,
            admitted=admitted,service_seconds=15))
        def reply(name,**values):print(c.canonical({'event':name,**values}),flush=True)
        async def wait_event(event,seconds):
            waiter=asyncio.create_task(event.wait())
            try:
                done,_=await asyncio.wait((task,waiter),timeout=seconds,return_when=asyncio.FIRST_COMPLETED)
                if task in done and not event.is_set():await task;raise c.CaptureError('combined-early-exit')
                if not event.is_set():raise c.CaptureError('combined-event-timeout')
            finally:
                waiter.cancel();await asyncio.gather(waiter,return_exceptions=True)
        try:
            await wait_event(bound,4)
            reply('bound',upstream_attempts=0,credential_descriptor_closed=True)
            for command in ('peer','start','retire','stop'):
                if await asyncio.wait_for(reader.readline(),10)!=(command+'\n').encode():
                    raise c.CaptureError('combined-command-order')
                if command=='peer':
                    await wait_event(peer_ready,4)
                    reply('peer',peer_uid_verified=pipe_fd==-1,upstream_attempts=0)
                elif command=='start':
                    admitted.set();await wait_event(started,4);reply('started',upstream_attempts=1)
                elif command=='retire':
                    await wait_event(retired,8)
                    retirement=c.strict_json(c.read_private(directory/'control/research-retired.json',262144))
                    if retirement['discovery_continues'] is not (scenario=='normal'):
                        raise c.CaptureError('combined-discovery-retirement')
                    if scenario=='normal':
                        event=c.strict_json(peer.event('create',10));event['mint']='1'*31+'3'
                        peer.frames.put_nowait(c.canonical(event).encode())
                        # Count is independently checked by the actual Node consumer.
                        await asyncio.sleep(0.05)
                    reply('retired',cleanup=retirement['research']['cleanup']['outcome'],admission_closed=True)
                else:
                    shutdown.set();receipt=await asyncio.wait_for(asyncio.shield(task),5)
                    if not peer.closed:raise c.CaptureError('combined-close')
                    reply('closed',connection_closed=True)
            return receipt
        finally:
            shutdown.set()
            if not task.done():
                task.cancel();await asyncio.gather(task,return_exceptions=True)
            input_transport.close()
    log=io.StringIO()
    STAGE="session"
    with redirect_stderr(log):
        result=asyncio.run(exercise())
        STAGE="export"
        exported=export_session(directory/'control/capture',directory/'control/session.jsonl',directory/'export')
        STAGE="restore"
        restored=restore_session(directory/'export/session.zip',exported['bundle_sha256'],directory/'restore')
    STAGE="diagnostics"
    if DIAGNOSTIC.search(log.getvalue()):
        c.exclusive_file(directory/'diagnostic-categories.json',c.raw({'categories':DIAGNOSTIC.findall(log.getvalue())}))
        raise c.CaptureError('combined-diagnostic')
    STAGE="replay"
    if exported['measurement']!=restored['measurement']:raise c.CaptureError('combined-replay')
    STAGE="sources"
    if c.read_private(directory/'manifest.json',65536)!=raw or manifest['source_sha256']!=c.pins():
        raise c.CaptureError('combined-source-drift')
    receipt={'schema_version':1,'manifest_sha256':c.digest(raw),'shared':result,
             'session_bundle_sha256':exported['bundle_sha256'],'session_bundle_bytes':exported['bundle_bytes'],
             'capture':restored['capture'],'measurement':restored['measurement'],
             'credential_descriptor_closed':True,'diagnostics_clean':True,
             'complete_session_replayed':True,'provider_connection_opened':False,'real_credential_used':False,
             'internet_and_dns_blocked':True,'child_process_creation_blocked':True,
             'parent_death_sigkill':True,'resources':manifest['resources']}
    # Scan before terminal publication, never publish a tainted success receipt.
    STAGE="secret-scan"
    for path in directory.rglob('*'):
        if path.is_file() and any(v in path.read_bytes() for v in variants):raise c.CaptureError('combined-secret')
    c.exclusive_file(directory/'worker-result.json',c.raw(receipt))


if __name__=='__main__':
    try:
        if len(sys.argv)!=7:raise RuntimeError('arguments')
        run(sys.argv[1],sys.argv[2],int(sys.argv[3]),int(sys.argv[4]),sys.argv[5],int(sys.argv[6]))
    except BaseException:
        try:c.exclusive_file(Path(sys.argv[1])/'worker-failure.json',c.raw({'stage':STAGE}))
        except BaseException:pass
        sys.exit(1)
