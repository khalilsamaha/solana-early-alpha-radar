"""New guarded application boundary for the existing combined acceptance runner."""
from contextlib import ExitStack
import os
from pathlib import Path
import time
from unittest.mock import patch
import guarded_session as guarded
import handoff_evidence as evidence
import check_combined as combined
c=combined.c;v=combined.v;app=v.native_scanner.application
CASES=('normal-service-exclusion','deadline-before-shared','deadline-after-shared',
       'service-lock-replaced','lost-service-completion','changed-application-storage')
PHASE_SECONDS={'disable_restart':30,'stop':30,'shared':60,'start_original':30,'restore_restart':30}


def exercise(root,registry,backend,name,*,development=False):
    c.check(name in CASES and (not development or name!='changed-application-storage'),'guarded-case')
    service=root/'service';service_sha=guarded.service.provision(service,backend.target)
    c.write_new(root/'service-path.json',c.raw({'directory':str(service),'contract_sha256':service_sha}))
    plan,sha,paths=combined.prepare(root,registry,backend,development,application=not development,
                                    service_contract_sha256=service_sha)
    offset=0.0
    guard=guarded.GuardedSharedPrepared(backend,plan,sha,paths,service_directory=service,service_sha256=service_sha,
        phase_seconds=PHASE_SECONDS,mode='session-scanner-normal' if development else app.MODE,
        clock=lambda:time.monotonic()+offset)
    result={'schema':1,'case':name,'status':'guarded-case-failed-live-blocked','started_utc':c.now(),
            'manifest_sha256':sha,'service_contract_sha256':service_sha,'registry':str(registry),
            'development':development,'commands':[],'fault_reached':False,'active_contender_refused':False,
            'consumed_attempt_refused':False,'clock_offset_injected':False,
            'production_modified':False,'provider_connection_opened':False,'activation_authorized':False}
    dispatch=backend.mutate;write=guarded.service.p.write_at;supervise=v.run
    def mutate(action,cid):result['commands'].append(action);return dispatch(action,cid)
    backend.mutate=mutate
    def reached(stage,**details):
        c.check(not result['fault_reached'],'guarded-fault-repeated');result['fault_reached']=True
        c.write_new(root/'fault-ready.json',c.raw({'schema':1,'case':name,'stage':stage,'manifest_sha256':sha,**details}))
    def lost(fd,filename,value):
        if filename==guarded.service.RESULT:
            reached('after-original-restoration-before-service-completion');raise OSError('fixture-lost-service-completion')
        return write(fd,filename,value)
    def expired(*args,**kwargs):
        nonlocal offset
        value=supervise(*args,**kwargs)
        c.check(value['outcome']==v.SUCCESS,'guarded-expiry-stage-not-reached')
        reached('after-actual-shared-shutdown-before-bridge-confirmation')
        offset+=PHASE_SECONDS['shared'];result['clock_offset_injected']=True
        return value
    try:
        with guard.open() as ctrl:
            if name=='normal-service-exclusion':
                contender=guarded.service.Lease(service,service_sha,backend.target,'f'*64,root/'other-output')
                try:
                    with contender:raise ValueError('guarded-contender-admitted')
                except ValueError as exc:c.check(exc.args==('service-coordinator-active',),'guarded-contender-refusal')
                result['active_contender_refused']=True
            try:
                with ExitStack() as stack:
                    if name=='lost-service-completion':stack.enter_context(patch.object(guarded.service.p,'write_at',side_effect=lost))
                    if name=='deadline-after-shared':stack.enter_context(patch.object(v,'run',side_effect=expired))
                    if name=='service-lock-replaced':
                        lock=service/guarded.service.LOCK;lock.rename(service/'retained-original-lock')
                        c.write_new(lock,b'');reached('service-lock-replaced-before-first-mutation')
                    ctrl.step('disable_restart');ctrl.step('stop')
                    if name=='deadline-before-shared':
                        reached('original-stopped-before-supervisor-entry')
                        offset+=guard.plan['aggregate_seconds'];result['clock_offset_injected']=True
                    guard.run_shared()
                    if name=='changed-application-storage':
                        row=c.parse(c.read(registry/v.RESULT,262144));actor=row['scanner']['actor']
                        files=actor['application_storage']['file_sha256']
                        names=sorted(key for key in files if key!='radar.sqlite')
                        c.check(names,'guarded-additional-storage-missing')
                        # Closed SQLite can legitimately retain empty sidecars.
                        # Mutate an existing nonempty auxiliary file, not a size
                        # assumption about the first filename in sorted order.
                        selected=None
                        for candidate in names:
                            path=registry/app.DATA/candidate;raw=c.read(path,app.MAX_DATABASE)
                            c.check(c.digest(raw)==files[candidate],'guarded-storage-before-change')
                            if raw:selected=candidate;break
                        c.check(selected is not None,'guarded-additional-storage-empty')
                        c.write_new(root/'before-corruption.bin',raw)
                        changed=raw[:-1]+bytes([raw[-1]^1])
                        reached('nonprimary-application-file-after-shared-close',file=selected,
                                before_sha256=c.digest(raw),after_sha256=c.digest(changed),bytes=len(raw))
                        with path.open('r+b') as stream:
                            c.check(stream.write(changed)==len(changed),'guarded-corruption-write');stream.flush();os.fsync(stream.fileno())
                    ctrl.step('start_original');ctrl.step('restore_restart');guard.complete()
            except (ValueError,OSError) as exc:
                wanted={'deadline-before-shared':'budget-aggregate-expired','deadline-after-shared':'budget-phase-expired',
                    'service-lock-replaced':'service-identity-changed','lost-service-completion':'fixture-lost-service-completion',
                    'changed-application-storage':'application-storage-evidence'}
                c.check(name in wanted and result['fault_reached'] and exc.args==(wanted[name],),'guarded-unexpected-refusal')
                result['expected_refusal']=wanted[name]
            else:c.check(name=='normal-service-exclusion','guarded-fault-missed')
        state=combined.pc.inspect(registry);result['control_recovery']=state
        restored=name in ('normal-service-exclusion','lost-service-completion')
        wanted=[] if name=='service-lock-replaced' else ['disable_restart','stop']
        if restored:wanted+=['start_original','restore_restart']
        c.check(result['commands']==wanted and state['original_restored'] is restored,'guarded-control-disposition')
        c.check(state['pending_action']==('start_original' if name=='changed-application-storage' else None),'guarded-pending-disposition')
        if name!='service-lock-replaced':
            other=guarded.service.Lease(service,service_sha,backend.target,'e'*64,root/'yet-another-output')
            try:
                with other:raise ValueError('guarded-consumed-admitted')
            except ValueError as exc:c.check(exc.args==('service-attempt-consumed',),'guarded-consumed-refusal')
            result['consumed_attempt_refused']=True
        result['service_recovery']=guarded.service.inspect(service,service_sha)
        c.check(result['service_recovery']['status']==('completion-recorded-attempt-consumed' if name=='normal-service-exclusion'
                else 'attempt-consumed-completion-unconfirmed'),'guarded-service-disposition')
        control=Path(paths['capture'])/'supervised-session'
        if control.exists():
            exported=combined.evidence.export(control,Path(paths['export'])/'session')
            restored_capture=combined.evidence.restore(Path(paths['export'])/'session/evidence.zip',exported['sha256'],Path(paths['restore'])/'session')
            c.check(restored_capture==exported['assessment'],'guarded-capture-replay');result['capture_preservation']=exported
        else:c.check(name in ('deadline-before-shared','service-lock-replaced'),'guarded-capture-unavailable')
        result['status']='guarded-case-passed-live-blocked';return result
    finally:
        backend.mutate=dispatch;result['finished_utc']=c.now();c.write_new(root/'result.json',c.raw(result))


def preserve(root,registry):
    service=c.parse(c.read(root/'service-path.json',4096));out=root/'handoff';out.mkdir(mode=0o700)
    receipt=evidence.export(root,registry,Path(service['directory']),out/'evidence.zip')
    c.write_new(out/'report.json',c.raw(receipt))
    case=c.parse(c.read(root/'result.json',2*1024**2))
    if case['status']=='guarded-case-passed-live-blocked':
        expected='closed-restored-offline-handoff-evidence' if case['case']=='normal-service-exclusion' else 'quarantined-handoff-evidence'
        c.check(receipt['assessment']['classification']==expected,'guarded-portable-disposition')
        if case['case']=='normal-service-exclusion' and not case['development']:
            c.check(receipt['assessment']['components']['native_application_verified'] and
                    receipt['assessment']['components']['native_disposal_verified'],'guarded-native-package-required')
    return receipt


def preserve_partial(out):
    """One attempt per case, including failures; never repair/retry partial exports."""
    results={}
    for name in CASES:
        root=out/name
        if not (root/'service-path.json').exists() or (root/'handoff').exists():continue
        try:
            path=c.parse(c.read(root/'registry-path.json',4096));results[name]=preserve(root,Path(path['registry']))
        except Exception:results[name]={'status':'portable-evidence-unavailable-retain-originals','activation_authorized':False}
    return results
