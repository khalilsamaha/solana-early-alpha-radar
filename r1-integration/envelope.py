"""Immutable variable-session evidence and injected transfer; no remote CLI."""
from contextlib import ExitStack
import io
import os
from pathlib import Path
import shutil
import stat
import struct
import tempfile
import zipfile
import common as c
import preserve
import lifecycle
import contract
import session_bundle

CAPS={**preserve.CAPS,'request.json':65536,'cleanup.json':262144,
      'worker.json':262144,'worker-manifest.json':65536,'admission.json':65536,
      'retired.json':262144,'stopped.json':262144,'fault-ready.json':4096,'worker-failure.json':4096}
MAX_MANIFEST=65536
MAX_BYTES=sum(CAPS.values())+MAX_MANIFEST+8192
SPACE=512*1024**2


def pack(contents):
    if (not {'manifest.json','request.json','contract.json','cleanup.json'}<=set(contents)
            or not set(contents)<=set(CAPS)|{'manifest.json'}):raise c.CaptureError('envelope-members')
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_STORED) as z:
        for name,data in sorted(contents.items()):
            if type(data) is not bytes or len(data)>(MAX_MANIFEST if name=='manifest.json' else CAPS[name]):
                raise c.CaptureError('envelope-member-cap')
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.create_system=3;info.external_attr=0o100600<<16
            z.writestr(info,data)
    return out.getvalue()


def unpack(raw):
    if type(raw) is not bytes or not 22<=len(raw)<=MAX_BYTES:raise c.CaptureError('envelope-cap')
    end=struct.unpack('<4s4H2LH',raw[-22:])
    if (end[0]!=b'PK\x05\x06' or end[1:3]!=(0,0) or not 4<=end[3]==end[4]<=len(CAPS)+1
            or end[7] or not 1<=end[5]<=4096 or end[6]+end[5]!=len(raw)-22):
        raise c.CaptureError('envelope-directory')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        entries=z.infolist();names=[e.filename for e in entries]
        if len(set(names))!=len(names) or not set(names)<=set(CAPS)|{'manifest.json'}:
            raise c.CaptureError('envelope-members')
        for e in entries:
            cap=MAX_MANIFEST if e.filename=='manifest.json' else CAPS[e.filename]
            if (e.compress_type!=0 or e.flag_bits or e.extra or e.comment or e.create_system!=3
                    or e.external_attr>>16!=0o100600 or not 0<=e.file_size<=cap or e.compress_size!=e.file_size):
                raise c.CaptureError('envelope-format')
        contents={e.filename:z.read(e) for e in entries}
    if pack(contents)!=raw:raise c.CaptureError('envelope-noncanonical')
    return contents


def row(data):
    value=c.strict_json(data)
    if c.raw(value)!=data:raise c.CaptureError('envelope-json')
    return value


def assess(data):
    request=row(data['request.json']);cleanup=row(data['cleanup.json'])
    if (request.get('kind')!='r1-combined-offline-v1' or request.get('source_sha256')!=c.pins()
            or request.get('contract_sha256')!=c.digest(data['contract.json'])
            or request.get('live_launch_authorized') is not False):raise c.CaptureError('envelope-request')
    # Quiescence is asserted only for an owned isolated run whose parent reaped
    # all actors. This is not independent production/remote attestation.
    actors=cleanup.get('actors',[])
    if (cleanup.get('broker_reaped') is not True or not 2<=len(actors)<=3
            or cleanup.get('production_modified') is not False or cleanup.get('provider_connections_opened')!=0
            or cleanup.get('max_simultaneous_synthetic_owners')!=1
            or cleanup.get('request_sha256')!=c.digest(data['request.json'])):
        raise c.CaptureError('envelope-quiescence')
    for actor in actors:
        if actor.get('process_reaped') is not True:raise c.CaptureError('envelope-active-actor')
        container=actor['container']
        if request['development']:
            if container is not None:raise c.CaptureError('envelope-transport')
        elif not container or container.get('removed') is not True:raise c.CaptureError('envelope-container')
    base={k:v for k,v in data.items() if k in preserve.CAPS}
    assessment=preserve.classify(base,request['contract_sha256'])
    reasons=list(assessment['reasons'])
    if request.get('interrupt') is not None:
        fault=row(data.get('fault-ready.json',b'{}\n'))
        state=assessment['lifecycle_state']
        claim=row(data['claim.json'])
        if (request['interrupt']!='stop_shared' or not state or state['pending_action']!='stop_shared'
                or fault!={'action':'stop_shared','operation_id':lifecycle.operation_id(claim,6),
                           'request_sha256':c.digest(data['request.json'])}):
            raise c.CaptureError('envelope-fault-not-reached')
    terminal={'worker.json','worker-manifest.json','admission.json','retired.json','stopped.json'}
    if not terminal<=set(data):reasons.append('terminal-session-evidence-missing')
    else:
        worker,manifest,admission,retired,stopped=(row(data[k]) for k in
            ('worker.json','worker-manifest.json','admission.json','retired.json','stopped.json'))
        import profile
        if (manifest.get('source_sha256')!=request['source_sha256']
                or manifest.get('resources')!=profile.make(15)
                or manifest.get('resources')!=request.get('resources')
                or manifest.get('request_sha256')!=c.digest(data['request.json'])
                or manifest.get('scenario')!=request['scenario']
                or manifest.get('mode')!='offline-combined-integration'
                or manifest.get('transport')!=('pipe' if request['development'] else 'unix')
                or worker.get('manifest_sha256')!=c.digest(data['worker-manifest.json'])
                or worker!=cleanup.get('worker') or worker.get('shared')!=stopped
                or worker.get('resources')!=manifest['resources']
                or worker.get('diagnostics_clean') is not True
                or worker.get('provider_connection_opened') is not False
                or worker.get('real_credential_used') is not False
                or admission.get('source_sha256')!=request['source_sha256']
                or admission.get('kind')!='r1-separated-session-v1'
                or admission.get('live_launch_authorized') is not False
                or retired.get('admission_sha256')!=c.digest(data['admission.json'])
                or retired.get('research_cannot_rearm') is not True
                or stopped.get('admission_sha256')!=c.digest(data['admission.json'])
                or stopped.get('retirement_sha256')!=c.digest(data['retired.json'])
                or stopped.get('local_upstream_closed') is not True
                or stopped.get('live_launch_authorized') is not False
                or stopped.get('research')!=retired.get('research')):
            raise c.CaptureError('envelope-terminal-binding')
        if (worker.get('capture')!=assessment['capture'] or worker.get('measurement')!=assessment['measurement']):
            raise c.CaptureError('envelope-independent-replay')
        if not reasons:
            # Recreate the inner package on copies, validating its claimed exact hash.
            with tempfile.TemporaryDirectory(prefix='r1-envelope-replay-') as tmp:
                root=Path(tmp);cap=root/'capture';cap.mkdir(mode=0o700)
                c.exclusive_file(cap/'ticks.db',data['capture.db']);c.exclusive_file(cap/'capture.lock',b'')
                c.exclusive_file(root/'session.jsonl',data['measurement.jsonl'])
                replay=session_bundle.export_session(cap,root/'session.jsonl',root/'export')
                if (replay['bundle_sha256']!=worker['session_bundle_sha256']
                        or replay['bundle_bytes']!=worker['session_bundle_bytes']):
                    raise c.CaptureError('envelope-inner-hash')
    return {'classification':'quarantined-incomplete-evidence' if reasons else 'complete-replayed-evidence',
            'reasons':reasons,'capture':assessment['capture'],'measurement':assessment['measurement'],
            'lifecycle_state':assessment['lifecycle_state'],'live_launch_authorized':False,
            'automatic_resume_allowed':False,'retention_verified':False,'production_handoff_verified':False}


def verify(raw,expected_sha):
    if not isinstance(expected_sha,str) or c.digest(raw)!=expected_sha:raise c.CaptureError('envelope-checksum')
    contents=unpack(raw);manifest=row(contents.pop('manifest.json'))
    expected={'schema_version':1,'kind':'r1-combined-envelope-v1','source_sha256':c.pins(),
              'members':{k:{'bytes':len(v),'sha256':c.digest(v)} for k,v in contents.items()},
              'assessment':assess(contents)}
    if c.raw(manifest)!=c.raw(expected):raise c.CaptureError('envelope-binding')
    return contents,manifest


def snapshot(control):
    b=control/'runtime/broker'
    paths={'request.json':control/'request.json','contract.json':control/'contract.json',
           'cleanup.json':control/'cleanup.json','claim.json':control/'registry/claim.json',
           'lifecycle.jsonl':control/'journal/events.jsonl','worker.json':b/'worker-result.json',
           'worker-manifest.json':b/'manifest.json','admission.json':b/'control/admission.json',
           'retired.json':b/'control/research-retired.json','stopped.json':b/'control/stopped.json',
           'capture.db':b/'control/capture/ticks.db','capture-journal':b/'control/capture/ticks.db-journal',
           'measurement.jsonl':b/'control/session.jsonl','fault-ready.json':control/'fault-ready.json',
           'worker-failure.json':b/'worker-failure.json'}
    return {k:c.read_private(p,CAPS[k]) for k,p in paths.items() if p.exists() or p.is_symlink()}


def preflight(output):
    output=c.path_without_links(output)
    if output.exists() or shutil.disk_usage(output.parent).free<SPACE:raise c.CaptureError('envelope-output-space')
    return output


def export(control,output):
    control=c.path_without_links(control);output=preflight(output)
    if control==output or control in output.parents:raise c.CaptureError('envelope-output-overlap')
    before=c.pins()
    with ExitStack() as stack:
        stack.enter_context(preserve.existing_lock(control/'registry/r1-supervisor.lock'))
        for path in (control/'runtime/broker/control/capture.lock',control/'runtime/broker/control/capture/capture.lock'):
            if path.exists():stack.enter_context(preserve.existing_lock(path))
        data=snapshot(control);assessment=assess(data)
        manifest={'schema_version':1,'kind':'r1-combined-envelope-v1','source_sha256':before,
                  'members':{k:{'bytes':len(v),'sha256':c.digest(v)} for k,v in data.items()},'assessment':assessment}
        raw=pack({**data,'manifest.json':c.raw(manifest)});verify(raw,c.digest(raw))
        if snapshot(control)!=data or c.pins()!=before:raise c.CaptureError('envelope-source-drift')
    output.mkdir(mode=0o700);c.exclusive_file(output/'evidence.zip',raw)
    result={'sha256':c.digest(raw),'bytes':len(raw),'assessment':assessment}
    c.exclusive_file(output/'report.json',c.raw(result));return result


def restore(path,expected_sha,output):
    output=preflight(output);raw=c.read_private(path,MAX_BYTES);data,manifest=verify(raw,expected_sha)
    output.mkdir(mode=0o700)
    for name,value in data.items():c.exclusive_file(output/name,value)
    c.exclusive_file(output/'manifest.json',c.raw(manifest))
    if c.read_private(path,MAX_BYTES)!=raw:raise c.CaptureError('envelope-input-changed')
    return manifest['assessment']


def transfer(path,expected_sha,attempt,backend):
    """Internal injection boundary: no B2/credential/remote destination adapter."""
    attempt=preflight(attempt);raw=c.read_private(path,MAX_BYTES)
    _,manifest=verify(raw,expected_sha);before=c.pins()
    attempt.mkdir(mode=0o700)
    c.exclusive_file(attempt/'source.zip',raw)
    intent={'schema_version':1,'sha256':expected_sha,'bytes':len(raw),'source_sha256':before,
            'classification':manifest['assessment']['classification'],'automatic_retry_allowed':False}
    c.exclusive_file(attempt/'intent.json',c.raw(intent))
    backend.put(expected_sha,raw)  # one attempt; exception leaves consumed evidence
    c.exclusive_file(attempt/'upload.json',c.raw({'intent_sha256':c.digest(c.raw(intent)),'returned':True}))
    downloaded=backend.get(expected_sha,len(raw)+1)
    if type(downloaded) is not bytes or len(downloaded)!=len(raw) or downloaded!=raw:
        raise c.CaptureError('envelope-download')
    c.exclusive_file(attempt/'download.zip',downloaded)
    assessment=restore(attempt/'download.zip',expected_sha,attempt/'restore')
    if c.read_private(path,MAX_BYTES)!=raw or c.pins()!=before:raise c.CaptureError('envelope-transfer-drift')
    receipt={'intent_sha256':c.digest(c.raw(intent)),'archive_sha256':expected_sha,
             'assessment':assessment,'retention_verified':False,'live_launch_authorized':False}
    c.exclusive_file(attempt/'completion.json',c.raw(receipt));return receipt
