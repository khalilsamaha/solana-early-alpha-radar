"""One read-only configuration binding inspection; no control commands or tests."""
import argparse
import os
from pathlib import Path
import tempfile
import zipfile
import admission as a
import command_io
import accepted_readiness as accepted
import ownership
import check_retained
c=a.c
SAFE = check_retained.SAFE_CODES | {
    'admission-engine-target-drift','admission-restart-drift','admission-container-config-drift',
    'admission-mount-drift','admission-labels','admission-configuration-drift',
    'ownership-accepted-baseline-unavailable','target-report-digest','target-producer-mismatch',
    'target-report-unavailable','binding-source-changed'}


def pins():
    names=['r1-production-control/'+n for n in ('check_binding.py','accepted_readiness.py',
           'check_retained.py','README.md','test_admission.py','test_binding.py')]
    names += ['r1-production-review/ownership.py','r1-production-review/readiness.py',
              'r1-production-review/intake.py','r1-production-review/readiness_diagnostics.py',
              'r1-host-review/check.py','scripts/r1-production-binding-kali.sh']
    return {**a.pins(),**{n:c.digest((a.control.ROOT/n).read_bytes()) for n in names}}


def code(exc):
    if isinstance(exc,ValueError) and len(exc.args)==1 and type(exc.args[0]) is str and exc.args[0] in SAFE:
        return exc.args[0]
    return check_retained.diagnostic(exc)


def collect(baseline_root):
    report={'schema':1,'kind':'read-only-retained-target-binding','status':'binding-unavailable',
            'started_utc':c.now(),'baseline_report_sha256':accepted.BASELINE_SHA256,
            'production_modified':False,'provider_connection_opened':False,'activation_authorized':False,
            'raw_configuration_exported':False,'global_owner_exclusivity_verified':False,
            'automatic_resume_allowed':False,'command_observations':[]}
    stage='source-before'
    try:
        before=pins();report['source_sha256']=before
        stage='accepted-baseline';data=ownership.find_baseline(baseline_root,accepted.BASELINE_SHA256)
        stage='local-docker-path';ownership.i.host.trusted_local_docker()
        with tempfile.TemporaryDirectory(prefix='r1-binding-empty-config-') as temporary:
            cli=[ownership.i.host.DOCKER,'--config',temporary,'--host','unix://'+ownership.i.host.SOCKET]
            stage='exact-target-binding'
            # Constructor executes ONE inspect; no Control or Prepared object is opened.
            backend=a.BoundDocker(cli,data,accepted.BASELINE_SHA256,accepted.PRODUCER_PINS,
                lambda args,**kw:command_io.bounded(args,env=ownership.i.host.ENV,
                                                  events=report['command_observations'],**kw))
            binding=backend.admission
        stage='source-after';c.check(pins()==before,'binding-source-changed')
        report.update(status='target-binding-observed-live-blocked',binding=binding)
    except Exception as exc:
        report['failure']={'stage':stage,'code':code(exc)}
    report['finished_utc']=c.now()
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-root',required=True);parser.add_argument('--output-directory',required=True)
    args=parser.parse_args();os.umask(0o077);out=Path(args.output_directory).absolute()
    c.check(not out.exists() and all(not p.is_symlink() for p in (out,*out.parents)),'output')
    out.mkdir(mode=0o700)
    report=collect(args.baseline_root)
    c.write_new(out/'report.json',c.raw(report))
    with zipfile.ZipFile(out/'production-binding.zip','x',compression=zipfile.ZIP_STORED) as archive:
        archive.write(out/'report.json','report.json')
    print(report['status']);print(out/'production-binding.zip')
    return 0 if report['status']=='target-binding-observed-live-blocked' else 1


if __name__=='__main__':raise SystemExit(main())
