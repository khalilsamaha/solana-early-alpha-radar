"""Produce one private read-only production-context report and evidence archive."""
import argparse
from contextlib import redirect_stderr
import io
from pathlib import Path
import os
import tempfile
import unittest
import zipfile
import intake as i

ERRORS={'docker-timeout','docker-output-limit','docker-inspect-unavailable','local-docker-path-unavailable',
        'metadata-invalid','process-observation-unavailable','container-not-running','container-main-process-ambiguous',
        'container-or-process-changed','container-process-binding-unavailable','context-fields','context-identity',
        'context-target','context-state','context-started','context-boolean','context-init','context-user',
        'context-working-directory','context-restart','context-resource','context-swap','context-pids','context-network',
        'context-mount-count','context-mount-fields','context-mount-path','context-mount-alias','context-census',
        'context-changed','context-target-outside-census','context-process-binding','context-not-running','context-source-changed'}


def collect(config,*,offline):
    before=i.pins();started=i.stamp();observation=None;error=None
    if not offline:
        try:observation=i.observe(config)
        except (i.host.ReviewError,ValueError) as exc:error=str(exc) if str(exc) in ERRORS else 'observation-unavailable'
        except Exception:error='observation-unavailable'
    if i.pins()!=before:observation=None;error='context-source-changed'
    status=('production-context-offline-tests-only' if offline and error is None else
            'production-context-observed-rollout-blocked' if observation is not None else
            'production-context-unavailable-rollout-blocked')
    return {'schema':1,'status':status,'started_utc':started,'finished_utc':i.stamp(),
        'source_sha256':before,'target':i.host.TARGET,'observation_attempted':not offline,'observation':observation,'error':error,
        'production_modified':False,'container_exec_used':False,'environment_read':False,'argv_read':False,
        'mounted_file_contents_read':False,'credentials_exported':False,'provider_connection_opened':False,
        'activation_authorized':False,'automatic_resume_allowed':False,'full_gate_accepted':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-directory',required=True)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--offline',action='store_true');mode.add_argument('--observe-local-container',action='store_true')
    args=parser.parse_args();os.umask(0o077);out=Path(args.output_directory).absolute()
    i.check(not out.exists() and all(not p.is_symlink() for p in (out,*out.parents)),'output-existing-or-linked')
    out.mkdir(mode=0o700);log=io.StringIO()
    report={'schema':1,'status':'production-context-check-failed','observation_attempted':False,
            'observation':None,'activation_authorized':False,'production_modified':False}
    try:
        import test_intake,test_check_intake
        suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(module) for module in (test_intake,test_check_intake))
        with redirect_stderr(log):tests=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
        counts={'run':tests.testsRun,'failures':len(tests.failures),'errors':len(tests.errors),'skipped':len(tests.skipped)}
        report['tests']=counts
        i.check(tests.wasSuccessful() and not tests.skipped,'offline-tests-failed')
        with tempfile.TemporaryDirectory(prefix='r1-context-empty-config-') as temporary:
            report=collect(Path(temporary),offline=args.offline)
        report['tests']=counts
    except Exception:report['failure']='check-unavailable'
    finally:
        i.host.write_report(out/'report.json',report)
        i.host.write_report(out/'test-results.json',{'log':log.getvalue()})
        with zipfile.ZipFile(out/'production-context.zip','x',compression=zipfile.ZIP_STORED) as archive:
            for name in ('report.json','test-results.json'):archive.write(out/name,name)
    print(report['status']);print(out/'production-context.zip')
    return 1 if report['status']=='production-context-check-failed' else 0


if __name__=='__main__':raise SystemExit(main())
