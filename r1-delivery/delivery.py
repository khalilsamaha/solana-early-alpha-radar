"""Portable OFFLINE run evidence with all admission/finalization receipts."""
from contextlib import ExitStack
import io
from pathlib import Path
import re
import stat
import struct
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
sys.path.insert(0,str(REPO/'r1-orchestration'))
import orchestrate as o
from capture import CaptureError,canonical,digest,exclusive_file,private_directory,strict_json
from handoff import path_without_links,read_private

ROLES={'admission.json':'admission.json','cleanup.json':'cleanup.json',
       'finalization-intent.json':'finalization-intent.json','completion.json':'completion.json',
       'preservation-report.json':'preserved/report.json','restore-report.json':'restored/report.json',
       'evidence.zip':'preserved/evidence.zip'}
CAPS={name:o.preserve.MAX_ARCHIVE if name=='evidence.zip' else 65536 for name in ROLES}
CAPS['manifest.json']=65536
MAX_PACKAGE=sum(CAPS.values())+4096
KIND='r1-offline-receipt-complete-package-v1'


def pins():
    result=o.pins()
    for pattern in ('*.py','*.md'):
        for path in ROOT.glob(pattern):
            if path.is_symlink():raise CaptureError('delivery-source-link')
            result[str(path.relative_to(REPO))]=digest(path.read_bytes())
    return dict(sorted(result.items()))


def json_bytes(row):return (canonical(row)+'\n').encode()


def row(raw):
    value=strict_json(raw)
    if not isinstance(value,dict) or json_bytes(value)!=raw:raise CaptureError('delivery-noncanonical-json')
    return value


def pack(contents):
    if set(contents)!=set(CAPS):raise CaptureError('delivery-members')
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(contents):
            raw=contents[name]
            if type(raw) is not bytes or len(raw)>CAPS[name]:raise CaptureError('delivery-member-bound')
            entry=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));entry.create_system=3
            entry.external_attr=(stat.S_IFREG|0o600)<<16
            archive.writestr(entry,raw)
    return stream.getvalue()


def unpack(raw):
    if type(raw) is not bytes or not 22<=len(raw)<=MAX_PACKAGE or not raw.startswith(b'PK\x03\x04'):
        raise CaptureError('delivery-envelope')
    end=struct.unpack('<4s4H2LH',raw[-22:])
    # Bound the central directory before allowing ZipFile to allocate entries.
    if (end[0]!=b'PK\x05\x06' or end[1:3]!=(0,0) or end[3:5]!=(8,8)
            or end[7]!=0 or not 1<=end[5]<=2048 or end[6]+end[5]!=len(raw)-22):
        raise CaptureError('delivery-directory')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries=archive.infolist();names=[entry.filename for entry in entries]
        if len(entries)!=8 or set(names)!=set(CAPS) or archive.comment:raise CaptureError('delivery-members')
        for entry in entries:
            if (entry.compress_type!=zipfile.ZIP_STORED or entry.flag_bits!=0 or entry.extra or entry.comment
                    or entry.create_system!=3 or entry.external_attr>>16!=stat.S_IFREG|0o600
                    or not 0<=entry.file_size<=CAPS[entry.filename] or entry.compress_size!=entry.file_size):
                raise CaptureError('delivery-member-format')
        contents={entry.filename:archive.read(entry) for entry in entries}
    if pack(contents)!=raw:raise CaptureError('delivery-noncanonical-zip')
    return contents


def manifest_for(contents,inner):
    admission=row(contents['admission.json']);completion=row(contents['completion.json'])
    return {'schema_version':1,'kind':KIND,'source_sha256':pins(),
            'members':{k:{'bytes':len(v),'sha256':digest(v)} for k,v in contents.items()},
            'contract_sha256':inner['contract_sha256'],'scenario':admission['scenario'],
            'classification':inner['assessment']['classification'],
            'reconciliation_required':completion['reconciliation_required'],
            'scope':'offline-synthetic-evidence-only','live_launch_authorized':False,
            'automatic_resume_allowed':False,'full_gate_accepted':False}


def validate_receipts(contents,inner_contents,inner):
    """Re-use the accepted reconciler on disposable copies, never on production."""
    # In addition to orchestration bindings, require exact report contents.
    archive=contents['evidence.zip'];sha=digest(archive);size=len(archive)
    expected_saved={'schema_version':1,'status':'local-evidence-preserved-live-blocked',
        'archive_sha256':sha,'archive_bytes':size,'assessment':inner['assessment'],
        'members':inner['members'],'absent':inner['absent'],'source_sha256':o.preserve.pins(),
        'source_bytes_unchanged':True,'source_sqlite_connection_opened':False,
        'remote_upload_performed':False,'automatic_resume_allowed':False}
    expected_restored={'schema_version':1,'status':'local-evidence-restore-verified-live-blocked',
        'archive_sha256':sha,'archive_bytes':size,'assessment':inner['assessment'],
        'member_bytes_verified':True,'automatic_resume_allowed':False,'remote_preservation_verified':False}
    if (contents['preservation-report.json']!=json_bytes(expected_saved)
            or contents['restore-report.json']!=json_bytes(expected_restored)):
        raise CaptureError('delivery-report-binding')
    for name in ROLES:
        if name!='evidence.zip':row(contents[name])
    with tempfile.TemporaryDirectory(prefix='r1-receipt-review-') as tmp:
        root=Path(tmp)
        paths={'r1-supervisor.lock':b'','contract.json':inner_contents['contract.json'],
               'lifecycle-registry/r1-supervisor.lock':b'',
               'lifecycle-registry/claim.json':inner_contents['claim.json'],
               'lifecycle-journal/events.jsonl':inner_contents['lifecycle.jsonl'],
               'runtime/broker/capture/capture.lock':b''}
        paths.update({target:contents[name] for name,target in ROLES.items()})
        paths.update({'restored/'+name:value for name,value in inner_contents.items()})
        for key,target in (('capture.db','runtime/broker/capture/ticks.db'),
                           ('capture-journal','runtime/broker/capture/ticks.db-journal'),
                           ('measurement.jsonl','runtime/broker/session.jsonl')):
            if key in inner_contents:paths[target]=inner_contents[key]
        for name,value in paths.items():
            path=root/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True);exclusive_file(path,value)
        result=o.inspect(root)
    if not result['finalization_complete']:raise CaptureError('delivery-receipts-unverifiable')
    return result


def verify(raw,expected_sha):
    if not isinstance(expected_sha,str) or not re.fullmatch('[0-9a-f]{64}',expected_sha):
        raise CaptureError('delivery-external-checksum')
    if type(raw) is not bytes or digest(raw)!=expected_sha:raise CaptureError('delivery-transfer-checksum')
    before=pins();contents=unpack(raw);manifest=row(contents.pop('manifest.json'))
    inner_contents,inner=o.preserve.verify(contents['evidence.zip'])
    inspection=validate_receipts(contents,inner_contents,inner)
    if json_bytes(manifest)!=json_bytes(manifest_for(contents,inner)):raise CaptureError('delivery-manifest-binding')
    if pins()!=before:raise CaptureError('delivery-source-changed')
    return contents,manifest,inspection


def export(control,output):
    control,output=map(path_without_links,(control,output));private_directory(control)
    if output==control or control in output.parents:raise CaptureError('delivery-output-inside-source')
    initial=o.inspect(control)
    if not initial['finalization_complete']:raise CaptureError('delivery-source-not-finalized')
    before=pins()
    with ExitStack() as stack:
        for path in (control/'r1-supervisor.lock',control/'lifecycle-registry/r1-supervisor.lock',
                     control/'runtime/broker/capture/capture.lock'):
            stack.enter_context(o.preserve.existing_lock(path))
        identities={name:o.preserve.identity((control/target).lstat()) for name,target in ROLES.items()}
        contents={name:read_private(control/target,CAPS[name]) for name,target in ROLES.items()}
        _,inner=o.preserve.verify(contents['evidence.zip'])
        raw=pack({**contents,'manifest.json':json_bytes(manifest_for(contents,inner))})
        _,manifest,inspection=verify(raw,digest(raw))
        if inspection!=initial:raise CaptureError('delivery-source-binding-changed')
        for name,target in ROLES.items():
            if (read_private(control/target,CAPS[name])!=contents[name]
                    or o.preserve.identity((control/target).lstat())!=identities[name]):
                raise CaptureError('delivery-source-changed')
    if o.inspect(control)!=initial or pins()!=before:raise CaptureError('delivery-source-changed')
    output.mkdir(mode=0o700)
    exclusive_file(output/'package.zip',raw)
    report={'schema_version':1,'status':'local-receipt-complete-package-verified-live-blocked',
            'package_sha256':digest(raw),'package_bytes':len(raw),'source_sha256':before,
            'classification':manifest['classification'],'reconciliation_required':manifest['reconciliation_required'],
            'source_bytes_unchanged':True,'remote_preservation_verified':False,
            'retention_verified':False,'automatic_resume_allowed':False,'live_launch_authorized':False}
    exclusive_file(output/'report.json',json_bytes(report))
    return report


def restore(package,expected_sha,output):
    before=pins();raw=read_private(package,MAX_PACKAGE);contents,manifest,inspection=verify(raw,expected_sha)
    output=path_without_links(output);output.mkdir(mode=0o700)
    # Fixed flat receipts and an evidence restore; never a resumable service tree.
    for name,value in contents.items():exclusive_file(output/name,value)
    exclusive_file(output/'manifest.json',json_bytes(manifest))
    replay=o.preserve.restore(output/'evidence.zip',digest(contents['evidence.zip']),output/'replayed-evidence')
    if read_private(package,MAX_PACKAGE)!=raw or pins()!=before:raise CaptureError('delivery-package-or-source-changed')
    report={'schema_version':1,'status':'local-receipt-complete-restore-verified-live-blocked',
            'package_sha256':expected_sha,'package_bytes':len(raw),'receipts_verified':True,
            'evidence_assessment_verified':True,'classification':manifest['classification'],
            'reconciliation_required':inspection['reconciliation_required'],
            'inner_restore_report_sha256':digest(json_bytes(replay)),
            'remote_preservation_verified':False,'retention_verified':False,
            'automatic_resume_allowed':False,'live_launch_authorized':False}
    exclusive_file(output/'report.json',json_bytes(report));return report
