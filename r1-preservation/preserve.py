"""Local immutable evidence preservation. Interrupted bytes are quarantined, never repaired."""
from contextlib import contextmanager, ExitStack
import fcntl
import io
import os
from pathlib import Path
import re
import stat
import struct
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
sys.path.insert(0,str(REPO/'r1-registration'))
import contract
from capture import CaptureError, canonical, digest, exclusive_file, private_directory, strict_json
from handoff import path_without_links, read_private
import lifecycle
import session_bundle

CAPS={'contract.json':65536,'claim.json':4096,'lifecycle.jsonl':65536,
      'capture.db':32*1024**2,'capture-journal':32*1024**2+4096,'measurement.jsonl':8*1024**2}
MAX_MANIFEST=65536
MAX_ARCHIVE=sum(CAPS.values())+MAX_MANIFEST+4096
KIND='r1-preserved-session-evidence-v1'


def pins():
    result=contract.pins()
    for pattern in ('*.py','*.md'):
        for path in ROOT.glob(pattern):
            if path.is_symlink():raise CaptureError('preservation-source-link')
            result[str(path.relative_to(REPO))]=digest(path.read_bytes())
    return dict(sorted(result.items()))


def identity(st):
    return (st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_nlink,st.st_size,st.st_mtime_ns,st.st_ctime_ns)


@contextmanager
def existing_lock(path):
    # Never create a source lock, truncate evidence or infer quiescence from a PID.
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid()
                or before.st_mode&0o077 or before.st_nlink!=1 or before.st_size!=0
                or identity(before)!=identity(path.lstat())):
            raise CaptureError('preservation-lock-identity')
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:raise CaptureError('preservation-writer-active') from None
        yield
        if identity(os.fstat(fd))!=identity(before) or identity(path.lstat())!=identity(before):
            raise CaptureError('preservation-lock-replaced')
    finally:os.close(fd)


def snapshot(capture,journal,registry,lifecycle_directory,contract_path):
    targets={'contract.json':contract_path,'claim.json':registry/'claim.json',
             'lifecycle.jsonl':lifecycle_directory/'events.jsonl',
             'capture.db':capture/'ticks.db','capture-journal':capture/'ticks.db-journal',
             'measurement.jsonl':journal}
    present={}
    for name,path in targets.items():
        try:path.lstat()
        except FileNotFoundError:continue
        present[name]=read_private(path,CAPS[name])
    if 'contract.json' not in present:raise CaptureError('preservation-contract-missing')
    return present


def classify(contents,contract_sha):
    # All replay is on disposable copies. Never open the source SQLite database.
    state=None;capture_report=measurement=None;reasons=[]
    with tempfile.TemporaryDirectory(prefix='r1-classify-') as tmp:
        root=Path(tmp);exclusive_file(root/'contract.json',contents['contract.json'])
        try:registered=contract.load(root/'contract.json',contract_sha)
        except Exception:registered=None;reasons.append('contract-unverifiable')
        try:
            claim=strict_json(contents['claim.json'])
            state=lifecycle.replay(claim,contents['lifecycle.jsonl'])
            if (registered is None or claim['registration_id']!=contract_sha
                    or claim['source_digest']!=registered['source_digest']):
                reasons.append('lifecycle-contract-binding-mismatch')
            if not state['complete']:reasons.append('lifecycle-incomplete')
        except Exception:reasons.append('lifecycle-unverifiable')
        if 'capture-journal' in contents:
            # Even a cold/empty rollback file remains evidence; do not recover it.
            reasons.append('sqlite-rollback-evidence-present')
        elif not {'capture.db','measurement.jsonl'}<=set(contents):
            reasons.append('capture-or-measurement-missing')
        else:
            capture=root/'capture';capture.mkdir(mode=0o700)
            exclusive_file(capture/'ticks.db',contents['capture.db'])
            exclusive_file(capture/'capture.lock',b'')
            exclusive_file(root/'session.jsonl',contents['measurement.jsonl'])
            try:
                replay=session_bundle.export_session(capture,root/'session.jsonl',root/'replay')
                capture_report,measurement=replay['capture'],replay['measurement']
                if capture_report['capture_status']!='stopped':reasons.append('capture-not-terminal')
            except Exception:reasons.append('complete-session-replay-unavailable')
    return {'classification':'quarantined-incomplete-evidence' if reasons else 'complete-replayed-evidence',
            'reasons':reasons,'lifecycle_state':state,'capture':capture_report,'measurement':measurement,
            'automatic_resume_allowed':False,'live_launch_authorized':False,'full_gate_accepted':False,
            'retention_verified':False,'remote_preservation_verified':False}


def pack(contents):
    names=set(contents)
    if ('manifest.json' not in names or not names<=(set(CAPS)|{'manifest.json'})
            or 'contract.json' not in names or any(type(v) is not bytes for v in contents.values())):
        raise CaptureError('preservation-members')
    for name,raw in contents.items():
        if len(raw)>(MAX_MANIFEST if name=='manifest.json' else CAPS[name]):
            raise CaptureError('preservation-member-bound')
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(contents):
            entry=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));entry.create_system=3
            entry.external_attr=(stat.S_IFREG|0o600)<<16
            archive.writestr(entry,contents[name])
    return stream.getvalue()


def unpack(raw):
    if not 22<=len(raw)<=MAX_ARCHIVE or not raw.startswith(b'PK\x03\x04'):
        raise CaptureError('preservation-envelope')
    end=struct.unpack('<4s4H2LH',raw[-22:])
    if (end[0]!=b'PK\x05\x06' or end[1:3]!=(0,0) or not 2<=end[3]==end[4]<=7
            or end[7]!=0 or not 1<=end[5]<=2048 or end[6]+end[5]!=len(raw)-22):
        raise CaptureError('preservation-directory')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries=archive.infolist();names=[e.filename for e in entries]
        if (len(entries)!=end[3] or len(set(names))!=len(names) or archive.comment
                or not set(names)<=(set(CAPS)|{'manifest.json'}) or not {'manifest.json','contract.json'}<=set(names)):
            raise CaptureError('preservation-members')
        for e in entries:
            cap=MAX_MANIFEST if e.filename=='manifest.json' else CAPS[e.filename]
            if (e.compress_type!=zipfile.ZIP_STORED or e.flag_bits!=0 or e.extra or e.comment
                    or e.create_system!=3 or e.external_attr>>16!=stat.S_IFREG|0o600
                    or not 0<=e.file_size<=cap or e.compress_size!=e.file_size):
                raise CaptureError('preservation-member-format')
        contents={e.filename:archive.read(e) for e in entries}
    if pack(contents)!=raw:raise CaptureError('preservation-noncanonical')
    return contents


def verify(raw):
    source_pins=pins()
    contents=unpack(raw);manifest_raw=contents.pop('manifest.json')
    try:manifest=strict_json(manifest_raw)
    except Exception:raise CaptureError('preservation-manifest-json') from None
    expected_keys={'schema_version','kind','source_sha256','contract_sha256','members','absent','assessment'}
    if (not isinstance(manifest,dict) or set(manifest)!=expected_keys
            or type(manifest['schema_version']) is not int or manifest['schema_version']!=1
            or manifest['kind']!=KIND or manifest['source_sha256']!=source_pins
            or manifest['contract_sha256']!=digest(contents['contract.json'])
            or manifest['members']!={k:{'bytes':len(v),'sha256':digest(v)} for k,v in contents.items()}
            or manifest['absent']!=sorted(set(CAPS)-set(contents))
            or (canonical(manifest)+'\n').encode()!=manifest_raw):
        raise CaptureError('preservation-manifest-binding')
    if classify(contents,manifest['contract_sha256'])!=manifest['assessment']:
        raise CaptureError('preservation-assessment-mismatch')
    if pins()!=source_pins:raise CaptureError('preservation-verifier-source-changed')
    return contents,manifest


def preserve(capture,journal,registry,lifecycle_directory,contract_path,contract_sha,output):
    capture,journal,registry,lifecycle_directory,contract_path,output=map(path_without_links,
        (capture,journal,registry,lifecycle_directory,contract_path,output))
    if not isinstance(contract_sha,str) or not re.fullmatch(r'[0-9a-f]{64}',contract_sha):
        raise CaptureError('preservation-contract-checksum')
    directories=(capture,journal.parent,registry,lifecycle_directory)
    for directory in directories:
        private_directory(directory)
        if output==directory or directory in output.parents:raise CaptureError('preservation-output-inside-source')
    source_pins=pins()
    with ExitStack() as stack:
        stack.enter_context(existing_lock(registry/'r1-supervisor.lock'))
        stack.enter_context(existing_lock(capture/'capture.lock'))
        before={p:identity(p.lstat()) for p in directories}
        if set(p.name for p in capture.iterdir())-{'ticks.db','ticks.db-journal','capture.lock'}:
            raise CaptureError('preservation-unexpected-capture-member')
        data=snapshot(capture,journal,registry,lifecycle_directory,contract_path)
        if digest(data['contract.json'])!=contract_sha:raise CaptureError('preservation-contract-checksum')
        assessment=classify(data,contract_sha)
        manifest={'schema_version':1,'kind':KIND,'source_sha256':source_pins,'contract_sha256':contract_sha,
                  'members':{k:{'bytes':len(v),'sha256':digest(v)} for k,v in data.items()},
                  'absent':sorted(set(CAPS)-set(data)),'assessment':assessment}
        raw=pack({**data,'manifest.json':(canonical(manifest)+'\n').encode()})
        verify(raw)
        if (snapshot(capture,journal,registry,lifecycle_directory,contract_path)!=data
                or any(identity(p.lstat())!=before[p] for p in directories) or pins()!=source_pins):
            raise CaptureError('preservation-source-changed')
        report={'schema_version':1,'status':'local-evidence-preserved-live-blocked','archive_sha256':digest(raw),
                'archive_bytes':len(raw),'assessment':assessment,'members':manifest['members'],
                'absent':manifest['absent'],'source_sha256':source_pins,'source_bytes_unchanged':True,
                'source_sqlite_connection_opened':False,'remote_upload_performed':False,'automatic_resume_allowed':False}
    output.mkdir(mode=0o700)
    exclusive_file(output/'evidence.zip',raw)
    exclusive_file(output/'report.json',(canonical(report)+'\n').encode())
    return report


def restore(archive,expected_sha,output):
    if not isinstance(expected_sha,str) or not re.fullmatch(r'[0-9a-f]{64}',expected_sha):
        raise CaptureError('preservation-external-checksum')
    raw=read_private(archive,MAX_ARCHIVE)
    if digest(raw)!=expected_sha:raise CaptureError('preservation-transfer-checksum')
    contents,manifest=verify(raw);output=path_without_links(output);output.mkdir(mode=0o700)
    # Flat fixed members, not a runnable capture directory. No extraction APIs.
    for name,value in contents.items():exclusive_file(output/name,value)
    exclusive_file(output/'manifest.json',(canonical(manifest)+'\n').encode())
    if read_private(archive,MAX_ARCHIVE)!=raw:raise CaptureError('preservation-archive-changed')
    report={'schema_version':1,'status':'local-evidence-restore-verified-live-blocked',
            'archive_sha256':expected_sha,'archive_bytes':len(raw),'assessment':manifest['assessment'],
            'member_bytes_verified':True,'automatic_resume_allowed':False,'remote_preservation_verified':False}
    exclusive_file(output/'report.json',(canonical(report)+'\n').encode())
    return report
