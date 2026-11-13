"""Read retained fixed-package transfer evidence; never contact B2 or resume."""
import argparse
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'r1-remote'))
import remote as r

MAX_FILES=96
MAX_BYTES=4*1024*1024


def pins():
    result=r.pins()
    for p in sorted(ROOT.glob('*')):
        if p.suffix in ('.py','.md'):result[str(p.relative_to(ROOT.parent))]=r.digest(p.read_bytes())
    return result


def inventory(root):
    """Bound and hash all retained bytes; refuse links, special files and aliases."""
    r.d.private_directory(root);result={};total=0
    def visit(path,depth):
        nonlocal total
        if depth>8:raise r.CaptureError('review-depth')
        with os.scandir(path) as entries:
            for entry in entries:
                if len(result)>=MAX_FILES:raise r.CaptureError('review-file-bound')
                child=Path(entry.path);st=child.lstat();name=str(child.relative_to(root))
                if stat.S_ISDIR(st.st_mode):
                    r.d.private_directory(child);result[name]=['directory'];visit(child,depth+1)
                elif stat.S_ISREG(st.st_mode):
                    raw=r.read_private(child,min(MAX_BYTES-total,1024*1024));total+=len(raw)
                    result[name]=[len(raw),r.digest(raw)]
                else:raise r.CaptureError('review-special-file')
    visit(root,0);return result


def inspect(control):
    result={'schema_version':1,'status':'remote-transfer-unresolved','recorded_completion_verified':False,
        'remote_observed_now':False,'remote_preservation_verified':False,'retention_verified':False,
        'automatic_retry_allowed':False,'automatic_resume_allowed':False,'live_launch_authorized':False,
        'manual_reconciliation_required':True}
    stage='control'
    try:
        control=r.path_without_links(control);r.d.private_directory(control);source=pins()
        with r.d.o.preserve.existing_lock(control/'r1-supervisor.lock'):
            before=inventory(control);stage='intent'
            intent=r.d.row(r.read_private(control/'intent.json',65536))
            profile=intent.get('profile');size,sha=r.PROFILES[profile];key=intent['object_name']
            if not isinstance(key,str) or not re.fullmatch('package-[0-9a-f]{32}-'+sha+r'\.zip',key):
                raise r.CaptureError('review-object')
            expected={'schema_version':1,'scope':'accepted-synthetic-package-only','profile':profile,
                'package_sha256':sha,'package_bytes':size,'source_report_sha256':r.REPORT_SHA,
                'source_sha256':r.pins(),'object_name':key,'automatic_retry_allowed':False}
            if intent!=expected:raise r.CaptureError('review-intent')
            # This is the recorded intended destination, not an observed remote object.
            result.update(profile=profile,package_sha256=sha,recorded_remote_object=r.old.PREFIX+key)
            stage='acceptance'
            report_raw=r.read_private(control/'acceptance-report.json',1024*1024)
            if r.digest(report_raw)!=r.REPORT_SHA:raise r.CaptureError('review-report')
            acceptance=r.d.row(report_raw)
            if acceptance['source_sha256']!=r.d.pins():raise r.CaptureError('review-source')
            raw=r.read_private(control/'package.zip',size)
            if len(raw)!=size or r.digest(raw)!=sha:raise r.CaptureError('review-package')
            stage='retained-members'
            names={'r1-supervisor.lock','package.zip','acceptance-report.json','preflight','intent.json',
                   'upload-observation.json','downloaded.zip','restored','completion.json'}
            if {p.name for p in control.iterdir()}!=names:raise r.CaptureError('review-incomplete')
            stage='download'
            if r.read_private(control/'downloaded.zip',size)!=raw:raise r.CaptureError('review-download')
            ih=r.digest(r.d.json_bytes(intent))
            upload=r.d.row(r.read_private(control/'upload-observation.json',4096))
            if upload!={'intent_sha256':ih,'upload_returned':True,'remote_object':r.old.PREFIX+key}:
                raise r.CaptureError('review-upload-binding')
            stage='restore'
            with tempfile.TemporaryDirectory(prefix='r1-remote-reconcile-') as tmp:
                private=Path(tmp);r.exclusive_file(private/'package.zip',raw)
                restored=r.d.restore(private/'package.zip',sha,private/'restored')
                if restored!=acceptance['cases'][profile]['restored']:raise r.CaptureError('review-restore-binding')
                exact=inventory(private/'restored')
                if inventory(control/'preflight')!=exact or inventory(control/'restored')!=exact:
                    raise r.CaptureError('review-restored-bytes')
            stage='completion'
            completion=r.d.row(r.read_private(control/'completion.json',16384))
            expected_completion={'schema_version':1,'status':'synthetic-package-roundtrip-verified-retention-pending',
                'intent_sha256':ih,'package_sha256':sha,'restore_report_sha256':r.digest(r.d.json_bytes(restored)),
                'classification':restored['classification'],'reconciliation_required':restored['reconciliation_required'],
                'downloaded_bytes_verified':True,'receipts_verified':True,'remote_roundtrip_observed':True,
                'retention_verified':False,'production_backup_coverage_verified':False,
                'automatic_retry_allowed':False,'automatic_resume_allowed':False,'live_launch_authorized':False,
                'full_gate_accepted':False,'calls':[{'operation':op,'state':'completed'} for op in ('backend','upload','download')]}
            if completion!=expected_completion:raise r.CaptureError('review-completion')
            stage='unchanged-source'
            if inventory(control)!=before or pins()!=source:raise r.CaptureError('review-changed')
            result.update(status='retained-transfer-completion-verified-remote-unobserved',
                recorded_completion_verified=True,classification=restored['classification'],
                manual_reconciliation_required=restored['reconciliation_required'],
                evidence_reconciliation_required=restored['reconciliation_required'])
    except Exception:
        result.update(status='remote-transfer-unresolved',recorded_completion_verified=False,
                      manual_reconciliation_required=True,failure_stage=stage)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--control-directory',required=True)
    args=parser.parse_args(argv)
    result=inspect(args.control_directory)
    print(r.d.canonical(result))
    return 0 if result['recorded_completion_verified'] else 2


if __name__=='__main__':raise SystemExit(main())
