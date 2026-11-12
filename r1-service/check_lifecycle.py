"""Offline handoff acceptance with disposable native processes and replayable journals."""
import argparse
import io
import os
from pathlib import Path
import platform
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
sys.path[:0]=[str(REPO/'r1-data'),str(REPO/'r1-runtime')]
import check as core
import boundary
from capture import CaptureError,canonical,digest,exclusive_file,strict_json
from handoff import path_without_links,read_private
from provider_wire import dependency
import lifecycle as l
from offline_backend import Backend


def pins():
    result=boundary.pins()
    files=[*ROOT.glob('*.py'),ROOT/'README.md']
    result.update({str(p.relative_to(REPO)):digest(p.read_bytes()) for p in files})
    return dict(sorted(result.items()))


def tests():
    suite=unittest.TestLoader().discover(str(ROOT),pattern='test_*.py')
    r=unittest.TextTestRunner(stream=io.StringIO(),verbosity=2).run(suite)
    if not r.wasSuccessful() or not r.testsRun or r.skipped:raise CaptureError('lifecycle-tests-failed')
    return {'run':r.testsRun,'errors':0,'failures':0,'skipped':0}


def scenario(output,name,source_digest,*,failure=None,when=None,cleanup_failure=False):
    root=output/name;root.mkdir(mode=0o700)
    registry=root/'registry';journal=root/'journal';registry.mkdir(mode=0o700);journal.mkdir(mode=0o700)
    registration=digest(('offline:'+name).encode())
    backend=Backend(cleanup_failure=cleanup_failure)
    interrupted=False
    class Adapter:
        def perform(self,action,op,known):
            if action==failure and when=='before':raise OSError('synthetic-operation-interruption')
            result=backend.perform(action,op,known)
            if action==failure and when=='after':raise OSError('synthetic-confirmation-interruption')
            return result
    try:
        with l.Lifecycle(registry,journal,registration,source_digest) as c:
            for action in l.ACTIONS:
                try:c.step(action,Adapter())
                except CaptureError:
                    if action!=failure:raise
                    interrupted=True
                    count=len(backend.actions)
                    try:c.step(action,backend)
                    except CaptureError:pass
                    else:raise CaptureError('lifecycle-retry-admitted')
                    if len(backend.actions)!=count:raise CaptureError('lifecycle-retry-executed')
                    break
    finally:backend.close()
    claim=strict_json(read_private(registry/'claim.json',4096));raw=read_private(journal/'events.jsonl',l.MAX_LOG)
    state=l.replay(claim,raw)
    if (interrupted!=(failure is not None) or state['pending_action']!=failure
            or state['complete']!=(failure is None) or state['automatic_resume_allowed']
            or state['reconciliation_required']!=(failure is not None)):
        raise CaptureError('lifecycle-state-expectation')
    actors=backend.receipt()
    index=l.ACTIONS.index(failure) if failure else len(l.ACTIONS)
    expected_actions=list(l.ACTIONS[:index+(when=='after')]) if failure else list(l.ACTIONS)
    expected_restore=int(failure is None or failure=='restore_direct' and when=='after')
    if (actors['actions']!=expected_actions or not actors['all_fixture_processes_reaped']
            or actors['max_simultaneous_owner_processes']!=1 or actors['direct_restore_calls']!=expected_restore):
        raise CaptureError('lifecycle-process-expectation')
    other=root/'different-output';other.mkdir(mode=0o700)
    try:
        with l.Lifecycle(registry,other,digest(b'new-registration'),source_digest):pass
    except FileExistsError:pass
    else:raise CaptureError('lifecycle-new-output-rearmed')
    if read_private(journal/'events.jsonl',l.MAX_LOG)!=raw:raise CaptureError('lifecycle-evidence-changed')
    return ({'name':name,'interrupted':interrupted,'failure_action':failure,'failure_timing':when,
             'state':state,'native_processes':actors,'registry_reuse_refused':True,
             'journal_sha256':digest(raw),'journal_bytes':len(raw)},
            {'claim':claim,'journal':raw.decode('ascii')})


class Parser(argparse.ArgumentParser):
    def error(self,message):raise CaptureError('lifecycle-arguments')


def main(argv=None):
    output=None;created=False;stage='arguments'
    report={'schema_version':1,'status':'offline-lifecycle-failed-live-blocked','synthetic_only':True,
        'provider_connection_opened':False,'credentials_loaded':False,'production_modified':False,
        'actual_rollout_or_rollback_tested':False,'endpoint_and_restart_policy_simulated':True,
        'live_launch_authorized':False,'full_gate_accepted':False,'docker_used':False}
    try:
        parser=Parser(description=__doc__);parser.add_argument('--output-directory',required=True)
        args=parser.parse_args(argv);os.umask(0o077)
        output=path_without_links(args.output_directory);output.mkdir(mode=0o700);created=True
        core.block_internet();started=time.monotonic();before=pins();source_digest=digest(canonical(before).encode())
        stage='regressions';report.update(python=platform.python_version(),dependencies=dependency(),
            core_tests=core.run_checks(),lifecycle_tests=tests())
        cases=[];journals={}
        for name,kwargs in [('normal',{}),('cleanup-abort',{'cleanup_failure':True})]+[
            (when+'-'+action,{'failure':action,'when':when}) for action in l.ACTIONS for when in ('before','after')]:
            stage=name
            case,journal=scenario(output,name,source_digest,**kwargs);cases.append(case);journals[name]=journal
        stage='final-verification'
        after=pins()
        if before!=after:raise CaptureError('lifecycle-sources-changed')
        payload=(canonical({'schema_version':1,'scope':'offline-service-lifecycle','cases':journals})+'\n').encode()
        if len(payload)>512*1024:raise CaptureError('lifecycle-evidence-bound')
        exclusive_file(output/'journals.json',payload)
        report.update(status='offline-lifecycle-passed-live-blocked',source_sha256=after,source_digest=source_digest,
            cases=cases,scenario_count=len(cases),journals_sha256=digest(payload),journals_bytes=len(payload),
            elapsed_seconds=round(time.monotonic()-started,6))
        exclusive_file(output/'report.json',(canonical(report)+'\n').encode())
        print('Offline lifecycle passed; live remains blocked. Upload report.json and journals.json from:')
        print(output);return 0
    except BaseException:
        report['status']='offline-lifecycle-failed-live-blocked';report['failure_stage']=stage
        if created:
            try:exclusive_file(output/'report.json',(canonical(report)+'\n').encode())
            except Exception:pass
        print('Lifecycle review stopped; preserve the output directory and upload the available report. No acceptance granted.',file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())
