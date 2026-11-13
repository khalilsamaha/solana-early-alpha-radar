"""Fixed synthetic package B2 boundary; no operational CLI or retry path."""
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import time
import tempfile
import uuid

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'r1-delivery'))
import delivery as d
import backup_roundtrip as old
from capture import CaptureError,digest,exclusive_file
from handoff import path_without_links,read_private
from supervisor import owner_lock

REPORT_SHA='f6ca0fcaadd391a4579e8b34eabd6e9259745940c1290d1f6156202efd00179f'
PROFILES={
 'normal':(125546,'9492acc0b03653d1612304592fad470ecb9efb65c4a45f220ef139ef301988aa'),
 'cleanup-failure':(125620,'33c2291e227708a3db3edf104d1e5f28d423bc47058229e8106453138128c86c'),
 'shutdown-interruption':(119856,'d7a4ba524ab5fdb115a39cc5d9f7a5b72dcade24e5dae814f597446827b75795')}


def pins():
    result=d.pins()
    for p in sorted(ROOT.glob('*')):
        if p.suffix in ('.py','.md'):result[str(p.relative_to(ROOT.parent))]=digest(p.read_bytes())
    return result


def bounded(command,payload,cap,seconds):
    """Drain bounded stdout while writing stdin; terminate/reap on every failure.

    The existing root-owned timeout wrapper terminates the privileged subtree.
    The outer deadline is four seconds longer than that wrapper's deadline.
    """
    out=bytearray();offset=0;end=time.monotonic()+seconds
    with subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL,env=old.ENV) as p:
        try:
            with selectors.DefaultSelector() as sel:
                os.set_blocking(p.stdout.fileno(),False);sel.register(p.stdout,selectors.EVENT_READ)
                if payload:
                    os.set_blocking(p.stdin.fileno(),False);sel.register(p.stdin,selectors.EVENT_WRITE)
                else:p.stdin.close()
                while sel.get_map():
                    left=end-time.monotonic()
                    if left<=0:raise CaptureError('remote-process-deadline')
                    for key,_ in sel.select(min(left,.1)):
                        if key.fileobj is p.stdout:
                            raw=os.read(p.stdout.fileno(),min(65536,cap-len(out)+1))
                            if not raw:sel.unregister(p.stdout)
                            else:
                                out.extend(raw)
                                if len(out)>cap:raise CaptureError('remote-output-cap')
                        else:
                            offset+=os.write(p.stdin.fileno(),payload[offset:offset+65536])
                            if offset==len(payload):sel.unregister(p.stdin);p.stdin.close()
                if p.wait(timeout=max(.001,end-time.monotonic()))!=0:raise CaptureError('remote-process-exit')
        except BaseException:
            p.kill();p.wait()
            raise CaptureError('remote-process-failed') from None
    return bytes(out)


class B2:
    scope='b2-fixed-synthetic-package'
    def __init__(self,profile):
        if profile not in PROFILES:raise CaptureError('remote-profile')
        self.size,self.sha=PROFILES[profile];self.calls=[];self.key=None
        self.deadline=time.monotonic()+135;self.stopped=False

    def run(self,operation,key=None,raw=None):
        if self.stopped or len(self.calls)>=3 or time.monotonic()>=self.deadline:raise CaptureError('remote-consumed')
        if operation!=('backend','upload','download')[len(self.calls)]:raise CaptureError('remote-order')
        if operation=='backend':
            if key is not None or raw is not None:raise CaptureError('remote-backend-arguments')
            args=['listremotes','--long'];cap=4096
        else:
            if not isinstance(key,str) or not re.fullmatch('package-[0-9a-f]{32}-'+self.sha+r'\.zip',key):
                raise CaptureError('remote-object')
            remote=old.PREFIX+key
            if operation=='upload':
                if type(raw) is not bytes or len(raw)!=self.size or digest(raw)!=self.sha:raise CaptureError('remote-payload')
                self.key=key;args=['rcat',remote,'--size',str(self.size)];cap=0
            else:
                if key!=self.key or raw is not None:raise CaptureError('remote-download-identity')
                args=['cat',remote,'--count',str(self.size+1)];cap=self.size+1
        remaining=min(40,int(self.deadline-time.monotonic())-4)
        if remaining<1:raise CaptureError('remote-deadline')
        command=[old.SUDO,'-n',old.TIMEOUT,'--signal=TERM','--kill-after=2s',str(remaining)+'s',old.RCLONE,
            '--config',old.CONFIG,'--transfers','1','--checkers','1','--buffer-size','64Ki',
            '--b2-chunk-size','8Mi','--b2-upload-concurrency','1','--retries','1','--low-level-retries','1',
            '--contimeout','10s','--timeout','20s','--max-transfer','128Ki','--log-level','ERROR',*args]
        call={'operation':operation,'state':'attempted'};self.calls.append(call)
        try:
            data=bounded(command,raw or b'',cap,remaining+4)
            if operation=='backend':
                rows=[line.split() for line in data.decode('utf-8').splitlines()]
                matches=[r for r in rows if r and r[0]=='radar-b2:']
                if len(matches)!=1 or len(matches[0])<2 or matches[0][1]!='b2':raise CaptureError('remote-backend')
            call['state']='completed';return data
        except BaseException:
            self.stopped=True;call['state']='failed';raise CaptureError('remote-operation-failed') from None


def transfer(control,package,report_path,profile,client):
    """Single consumed intent; exact preflight before any credential boundary.

    Caller owns the transport. Only the offline checker is exposed as a CLI.
    This function grants no live collection or ongoing retention authority.
    """
    if profile not in PROFILES or type(client) is not B2:raise CaptureError('remote-profile-client')
    size,sha=PROFILES[profile]
    if (client.size,client.sha)!=(size,sha) or client.calls:raise CaptureError('remote-client-consumed')
    source=read_private(package,size);report_raw=read_private(report_path,1024*1024)
    if len(source)!=size or digest(source)!=sha or digest(report_raw)!=REPORT_SHA:raise CaptureError('remote-input-binding')
    report=d.row(report_raw)
    if report['source_sha256']!=d.pins() or report['status']!='offline-delivery-passed-remote-pending':
        raise CaptureError('remote-acceptance-binding')
    control=path_without_links(control);d.private_directory(control);before=pins()
    with owner_lock(control):
        if {p.name for p in control.iterdir()}!={'r1-supervisor.lock'}:raise CaptureError('remote-control-consumed')
        exclusive_file(control/'package.zip',source)
        exclusive_file(control/'acceptance-report.json',report_raw)
        preflight=d.restore(control/'package.zip',sha,control/'preflight')
        if preflight!=report['cases'][profile]['restored']:raise CaptureError('remote-preflight-binding')
        intent={'schema_version':1,'scope':'accepted-synthetic-package-only','profile':profile,
            'package_sha256':sha,'package_bytes':size,'source_report_sha256':REPORT_SHA,'source_sha256':before,
            'object_name':'package-'+uuid.uuid4().hex+'-'+sha+'.zip','automatic_retry_allowed':False}
        d.o.write(control,'intent.json',intent);stage='backend'
        try:
            old.trusted_programs();client.run('backend')
            stage='upload';client.run('upload',intent['object_name'],source)
            d.o.write(control,'upload-observation.json',{'intent_sha256':digest(d.json_bytes(intent)),
                        'upload_returned':True,'remote_object':old.PREFIX+intent['object_name']})
            stage='download';raw=client.run('download',intent['object_name'])
            if raw!=source:raise CaptureError('remote-download-mismatch')
            exclusive_file(control/'downloaded.zip',raw)
            stage='restore';restored=d.restore(control/'downloaded.zip',sha,control/'restored')
            if (restored!=preflight or pins()!=before or read_private(package,size)!=source
                    or read_private(control/'package.zip',size)!=source
                    or read_private(control/'acceptance-report.json',1024*1024)!=report_raw
                    or read_private(report_path,1024*1024)!=report_raw):
                raise CaptureError('remote-final-binding')
            stage='completion'
            result={'schema_version':1,'status':'synthetic-package-roundtrip-verified-retention-pending',
                'intent_sha256':digest(d.json_bytes(intent)),'package_sha256':sha,
                'restore_report_sha256':digest(d.json_bytes(restored)),
                'classification':restored['classification'],'reconciliation_required':restored['reconciliation_required'],
                'downloaded_bytes_verified':True,'receipts_verified':True,'remote_roundtrip_observed':True,
                'retention_verified':False,'production_backup_coverage_verified':False,
                'automatic_retry_allowed':False,'automatic_resume_allowed':False,'live_launch_authorized':False,
                'full_gate_accepted':False,'calls':client.calls}
            d.o.write(control,'completion.json',result)
            return result
        except BaseException:
            try:d.o.write(control,'failure.json',{'schema_version':1,'stage':stage,
                'intent_sha256':digest(d.json_bytes(intent)),'remote_object_may_exist':any(x['operation']=='upload' for x in client.calls),
                'calls':client.calls,'manual_reconciliation_required':True,'automatic_retry_allowed':False,
                'local_package_retained':True,'retention_verified':False})
            except Exception:pass
            raise CaptureError('remote-transfer-unresolved') from None
