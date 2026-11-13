"""One consumed registry, separated session, isolated handoff and evidence delivery."""
import os
from pathlib import Path
import signal
import tempfile
import uuid
import common as c
import contract
import lifecycle
from supervisor import owner_lock,termination_handlers
from adapters import Backend,reap
import envelope


class MemoryRemote:
    """Acceptance-only backend. Does not contact B2 or another service."""
    def __init__(self):self.objects={};self.calls=[]
    def put(self,key,raw):
        self.calls.append('put')
        if self.objects:raise c.CaptureError('mock-remote-reuse')
        self.objects[key]=raw
    def get(self,key,cap):
        self.calls.append('get');raw=self.objects[key]
        if len(raw)>cap:raise c.CaptureError('mock-remote-cap')
        return raw


def run(registry,output,*,scenario='normal',development=False,interrupt=None):
    if scenario not in ('normal','cleanup-failure') or type(development) is not bool:
        raise c.CaptureError('combined-scope')
    if interrupt not in (None,'stop_shared'):raise c.CaptureError('combined-fault-scope')
    registry,output=c.path_without_links(registry),envelope.preflight(output)
    if registry==output or registry in output.parents or output in registry.parents:
        raise c.CaptureError('combined-overlap')
    before=c.pins()
    with owner_lock(registry),termination_handlers():
        if (registry/'claim.json').exists():raise c.CaptureError('combined-registry-consumed')
        output.mkdir(mode=0o700)
        (output/'registration').mkdir(mode=0o700);frozen=contract.freeze(output/'registration')
        raw=c.read_private(output/'registration/contract.json',65536)
        c.exclusive_file(output/'contract.json',raw)
        frozen=contract.load(output/'contract.json',c.digest(raw))
        request={'schema_version':1,'kind':'r1-combined-offline-v1','attempt_id':uuid.uuid4().hex,
                 'registry':str(registry),'output':str(output),'source_sha256':before,
                 'contract_sha256':c.digest(raw),'resources':__import__('profile').make(15),'scenario':scenario,'development':development,
                 'interrupt':interrupt,'live_launch_authorized':False,'automatic_resume_allowed':False}
        c.exclusive_file(output/'request.json',c.raw(request))
        c.exclusive_file(registry/'claim.json',c.raw({'request_sha256':c.digest(c.raw(request)),'output':str(output)}))
        for folder in ('registry','journal','runtime'):(output/folder).mkdir(mode=0o700)
        failed=False;backend=None;fault_reached=False;cleanup_error=False
        with tempfile.TemporaryDirectory(prefix='r1-combined-ipc-') as tmp:
            try:
                with lifecycle.Lifecycle(output/'registry',output/'journal',c.digest(raw),frozen['source_digest']) as journal:
                    backend=Backend(output/'runtime',Path(tmp),scenario,request_sha256=c.digest(c.raw(request)),pipe_only=development)
                    backend.prepare()
                    class Adapter:
                        def perform(self,action,op,known):
                            nonlocal fault_reached
                            if action==interrupt:
                                c.exclusive_file(output/'fault-ready.json',c.raw({'action':action,'operation_id':op,
                                    'request_sha256':c.digest(c.raw(request))}))
                                fault_reached=True;reap(backend.broker)
                                raise c.CaptureError('combined-injected-interruption')
                            return backend.perform(action,op,known)
                    for action in lifecycle.ACTIONS:journal.step(action,Adapter())
            except BaseException:
                failed=True
            finally:
                saved={s:signal.signal(s,signal.SIG_IGN) for s in (signal.SIGTERM,signal.SIGINT)}
                try:
                    if backend:
                        try:backend.close()
                        except BaseException:cleanup_error=True
                finally:
                    for s,h in saved.items():signal.signal(s,h)
        if backend is None:raise c.CaptureError('combined-no-backend')
        cleanup=backend.receipt();cleanup['request_sha256']=c.digest(c.raw(request))
        c.exclusive_file(output/'cleanup.json',c.raw(cleanup))
        if cleanup_error:raise c.CaptureError('combined-cleanup-unconfirmed')
        state=lifecycle.inspect(output/'registry',output/'journal')
        if failed is state['complete'] or (interrupt is not None and not fault_reached):
            raise c.CaptureError('combined-outcome-mismatch')
        if not state['complete'] and interrupt is None:raise c.CaptureError('combined-operation-failed')
        exported=envelope.export(output,output.parent/(output.name+'-envelope'))
        archive=output.parent/(output.name+'-envelope/evidence.zip')
        restored=envelope.restore(archive,exported['sha256'],output.parent/(output.name+'-restore'))
        if restored!=exported['assessment']:raise c.CaptureError('combined-restore')
        remote=MemoryRemote()
        transferred=envelope.transfer(archive,exported['sha256'],output.parent/(output.name+'-transfer'),remote)
        if transferred['assessment']!=restored or remote.calls!=['put','get']:
            raise c.CaptureError('combined-transfer')
        if c.pins()!=before:raise c.CaptureError('combined-source-drift')
        result={'schema_version':1,'status':'combined-offline-evidence-live-blocked',
                'request_sha256':c.digest(c.raw(request)),'lifecycle':state,
                'envelope':exported,'mock_transfer':transferred,'cleanup':cleanup,
                'fault_reached':fault_reached,'provider_connection_opened':False,
                'production_modified':False,'remote_upload_performed':False,'live_launch_authorized':False}
        c.exclusive_file(output/'completion.json',c.raw(result));return result


def inspect(registry,output):
    """Read retained evidence without writing, locking anew, spawning or resuming."""
    registry,output=map(c.path_without_links,(registry,output))
    request_raw=c.read_private(output/'request.json',65536);request=envelope.row(request_raw)
    claim=envelope.row(c.read_private(registry/'claim.json',4096))
    if (request['registry']!=str(registry) or request['output']!=str(output)
            or request['source_sha256']!=c.pins()
            or claim!={'request_sha256':c.digest(request_raw),'output':str(output)}):
        raise c.CaptureError('combined-recovery-binding')
    state=lifecycle.inspect(output/'registry',output/'journal')
    complete=False
    if (output/'completion.json').exists():
        receipt=envelope.row(c.read_private(output/'completion.json',262144))
        if receipt.get('request_sha256')!=c.digest(request_raw):raise c.CaptureError('combined-completion-binding')
        evidence=c.read_private(output.parent/(output.name+'-envelope/evidence.zip'),envelope.MAX_BYTES)
        data,manifest=envelope.verify(evidence,receipt['envelope']['sha256'])
        if (data!=envelope.snapshot(output) or receipt['lifecycle']!=state
                or receipt['envelope']['assessment']!=manifest['assessment']):
            raise c.CaptureError('combined-recovery-evidence')
        complete=state['complete']
    return {'lifecycle':state,'automatic_resume_allowed':False,'live_launch_authorized':False,
            'reconciliation_required':not complete,'historical_evidence_only':True}
