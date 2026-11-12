"""One-attempt OFFLINE transfer protocol; no remote adapter or credentials."""
from pathlib import Path
import re
import tempfile
import uuid

import delivery as d
from capture import CaptureError,exclusive_file,private_directory,digest
from handoff import path_without_links,read_private
from supervisor import owner_lock


def completion_for(intent,restored):
    return {'schema_version':1,'status':'offline-transfer-rehearsal-passed-live-blocked',
            'intent_sha256':digest(d.json_bytes(intent)),'package_sha256':intent['package_sha256'],
            'package_bytes':intent['package_bytes'],'restore_report_sha256':digest(d.json_bytes(restored)),
            'classification':restored['classification'],'reconciliation_required':restored['reconciliation_required'],
            'downloaded_bytes_verified':True,'receipts_verified':True,'evidence_assessment_verified':True,
            'remote_upload_performed':False,'remote_preservation_verified':False,
            'retention_verified':False,'automatic_retry_allowed':False,
            'automatic_resume_allowed':False,'live_launch_authorized':False,'full_gate_accepted':False}


def inspect(control):
    """Verify stored receipts and replay disposable copies; never resume transfer."""
    result={'status':'transfer-reconciliation-required','finalization_complete':False,
            'automatic_retry_allowed':False,'remote_preservation_verified':False,'retention_verified':False}
    try:
        control=path_without_links(control);private_directory(control)
        with d.o.preserve.existing_lock(control/'r1-supervisor.lock'):
            expected_names={'r1-supervisor.lock','package.zip','intent.json','upload-observation.json',
                            'downloaded.zip','restored','completion.json'}
            if {p.name for p in control.iterdir()}!=expected_names:raise CaptureError('delivery-transfer-incomplete')
            intent,_=d.o.read(control,'intent.json');raw=read_private(control/'package.zip',d.MAX_PACKAGE)
            sha=digest(raw);key=intent['object_name']
            if not isinstance(key,str) or not re.fullmatch('evidence-[0-9a-f]{32}-'+sha+r'\.zip',key):
                raise CaptureError('delivery-transfer-object')
            expected_intent={'schema_version':1,'mode':'offline-local-transfer-rehearsal','object_name':key,
                'package_sha256':sha,'package_bytes':len(raw),'source_sha256':d.pins(),
                'automatic_retry_allowed':False,'remote_preservation_verified':False,
                'retention_verified':False,'live_launch_authorized':False}
            if d.json_bytes(intent)!=d.json_bytes(expected_intent):raise CaptureError('delivery-transfer-intent')
            observation,_=d.o.read(control,'upload-observation.json')
            if d.json_bytes(observation)!=d.json_bytes({'schema_version':1,'upload_returned':True,
                    'scope':'local-simulation-only','intent_sha256':digest(d.json_bytes(intent))}):
                raise CaptureError('delivery-transfer-observation')
            if read_private(control/'downloaded.zip',d.MAX_PACKAGE)!=raw:raise CaptureError('delivery-transfer-download')
            with tempfile.TemporaryDirectory(prefix='r1-transfer-review-') as tmp:
                restored=d.restore(control/'downloaded.zip',sha,Path(tmp)/'restore')
                expected={str(p.relative_to(Path(tmp)/'restore')):p for p in (Path(tmp)/'restore').rglob('*') if p.is_file()}
                actual={str(p.relative_to(control/'restored')):p for p in (control/'restored').rglob('*') if p.is_file()}
                if set(actual)!=set(expected):raise CaptureError('delivery-transfer-restored-members')
                for name,path in expected.items():
                    if read_private(actual[name],d.MAX_PACKAGE)!=path.read_bytes():raise CaptureError('delivery-transfer-restored-bytes')
            completion,_=d.o.read(control,'completion.json')
            if d.json_bytes(completion)!=d.json_bytes(completion_for(intent,restored)):
                raise CaptureError('delivery-transfer-completion')
            result.update(status='offline-transfer-rehearsal-verified-remote-pending',finalization_complete=True,
                          package_sha256=sha,reconciliation_required=restored['reconciliation_required'])
    except Exception:pass
    return result


class LocalMirror:
    """Explicit local test double. Cannot claim B2 or remote verification."""
    def __init__(self,directory):
        self.directory=path_without_links(directory);private_directory(self.directory)
        self.calls=[];self.key=None

    def upload(self,key,raw):
        if self.calls or Path(key).name!=key:raise CaptureError('delivery-transfer-order')
        self.calls.append('upload');self.key=key
        exclusive_file(self.directory/key,raw)

    def download(self,key,cap):
        if self.calls!=['upload'] or key!=self.key:raise CaptureError('delivery-transfer-order')
        self.calls.append('download')
        return read_private(self.directory/key,cap)


def rehearse(control,package,expected_sha,transport):
    """Intent precedes transport; final receipt follows independent restored bytes.

    The only exposed protocol is a local rehearsal, even with a test double.
    Control directories are durable single-use slots, never automatically reset.
    """
    control=path_without_links(control);private_directory(control)
    stage='preflight';intent=None
    with owner_lock(control):
        if set(p.name for p in control.iterdir())!={'r1-supervisor.lock'}:
            raise CaptureError('delivery-transfer-control-consumed')
        # Retain a frozen local package before invoking any transport operation.
        raw=read_private(package,d.MAX_PACKAGE);_,manifest,_=d.verify(raw,expected_sha);before=d.pins()
        exclusive_file(control/'package.zip',raw)
        intent={'schema_version':1,'mode':'offline-local-transfer-rehearsal',
                'object_name':'evidence-'+uuid.uuid4().hex+'-'+expected_sha+'.zip',
                'package_sha256':expected_sha,'package_bytes':len(raw),'source_sha256':before,
                'automatic_retry_allowed':False,'remote_preservation_verified':False,
                'retention_verified':False,'live_launch_authorized':False}
        d.o.write(control,'intent.json',intent)
        try:
            stage='upload';transport.upload(intent['object_name'],raw)
            d.o.write(control,'upload-observation.json',{'schema_version':1,'upload_returned':True,
                       'scope':'local-simulation-only','intent_sha256':digest(d.json_bytes(intent))})
            stage='download';downloaded=transport.download(intent['object_name'],len(raw)+1)
            if type(downloaded) is not bytes or downloaded!=raw:raise CaptureError('delivery-downloaded-bytes')
            exclusive_file(control/'downloaded.zip',downloaded)
            stage='independent-restore';restored=d.restore(control/'downloaded.zip',expected_sha,control/'restored')
            if (restored['classification']!=manifest['classification'] or d.pins()!=before
                    or read_private(package,d.MAX_PACKAGE)!=raw or read_private(control/'package.zip',d.MAX_PACKAGE)!=raw):
                raise CaptureError('delivery-final-source-check')
            stage='completion-publication'
            completion=completion_for(intent,restored)
            d.o.write(control,'completion.json',completion)
            return completion
        except BaseException:
            # Never retry/delete: upload failure may still leave a complete object.
            try:d.o.write(control,'failure.json',{'schema_version':1,'stage':stage,
                'intent_sha256':digest(d.json_bytes(intent)),'local_package_retained':True,
                'simulated_object_may_exist':True,'manual_reconciliation_required':True,
                'remote_preservation_verified':False,'automatic_retry_allowed':False})
            except Exception:pass
            raise CaptureError('delivery-transfer-rehearsal-failed') from None
