"""Fixed service registry and separate phase budgets on the accepted offline path.

Only newly owned IsolatedBoundDocker targets are accepted. Production control,
external-controller fencing and live profile approval are not supplied here.
"""
from contextlib import contextmanager
import time
import shared_session as shared
import service_registry as service
import handoff_budget as budget
c=shared.c;a=shared.a;pc=shared.control
CLAIM='guarded-session-claim.json';RESULT='guarded-session-result.json'


class GuardedSharedPrepared(shared.SharedPrepared):
    def __init__(self,backend,directory,manifest_sha256,paths,*,service_directory,service_sha256,
                 phase_seconds,mode='session-application-normal',clock=time.monotonic):
        c.check(type(backend) is a.IsolatedBoundDocker,'guarded-offline-fixture-required')
        super().__init__(backend,directory,manifest_sha256,paths,mode=mode)
        manifest,_=self.preparation()
        c.check(manifest['config']['service_contract_sha256']==service_sha256,'guarded-manifest-service-binding')
        self.plan=budget.build(backend.target,manifest,phase_seconds)
        self.timer=budget.Clock(self.plan,clock=clock)
        self.lease=service.Lease(service_directory,service_sha256,backend.target,manifest_sha256,self.registry)
        self.guarded_claim=None;self.pending_confirmation=None;self.finished=False;self.opened=False

    @contextmanager
    def open(self):
        c.check(not self.opened,'guarded-attempt-consumed');self.opened=True
        with self.lease:
            self.timer.start()
            self.guarded_claim={'schema':1,'kind':'guarded-offline-shared-session','manifest_sha256':self.sha,
                'service_contract_sha256':self.lease.sha,'service_attempt_sha256':c.digest(c.raw(self.lease.claim)),
                'budget':self.plan,'source_sha256':shared.pins(),'created_utc':c.now(),
                'global_owner_exclusivity_verified':False,'production_profile_accepted':False,
                'activation_authorized':False,'automatic_resume_allowed':False}
            c.write_new(self.registry/CLAIM,c.raw(self.guarded_claim))
            with super().open() as controller:
                self.check_guard();yield controller
                # No automatic completion, restart or restoration on context exit.

    def check_guard(self):
        self.lease.check();self.timer.check()
        c.check(self.guarded_claim is not None and
                c.read(self.registry/CLAIM,262144)==c.raw(self.guarded_claim) and
                self.guarded_claim['source_sha256']==shared.pins(),'guarded-claim-changed')

    def unchanged(self):
        self.check_guard();return super().unchanged()

    def gate(self,action):
        self.check_guard();return super().gate(action)

    def observe(self,cid):
        self.check_guard();row=super().observe(cid);self.check_guard()
        if self.pending_confirmation is not None:
            self.timer.end(self.pending_confirmation);self.pending_confirmation=None
        return row

    def before_dispatch(self,action,cid):
        self.check_guard()
        c.check(self.timer.active==action and cid==self.backend.target['id'],'guarded-dispatch-phase')

    def before_shared(self):
        self.check_guard();c.check(self.timer.active=='shared','guarded-shared-phase')

    def mutate(self,action,cid):
        self.check_guard();self.timer.begin(action)
        try:
            ack=super().mutate(action,cid);self.check_guard()
            self.pending_confirmation=action;return ack
        except BaseException:self.timer.poisoned=True;raise

    def run_shared(self):
        self.check_guard();self.timer.begin('shared')
        try:
            result=super().run_shared();self.timer.end('shared');return result
        except BaseException:
            self.timer.poisoned=True
            if self.controller is not None:self.controller.poisoned=True
            raise

    def complete(self):
        """Record confirmed restoration; never dispatch a control operation."""
        self.check_guard();c.check(not self.finished,'guarded-completion-reuse')
        state=self.closed()
        c.check(state['original_restored'] and state['pending_action'] is None and
                self.pending_confirmation is None,'guarded-restoration-required')
        timing=self.timer.receipt()
        result={'schema':1,'kind':'guarded-offline-shared-session-complete',
                'claim_sha256':c.digest(c.raw(self.guarded_claim)),
                'control_events_sha256':c.digest(c.read(self.registry/'events.jsonl',65536)),
                'shared_result_sha256':c.digest(c.read(self.registry/shared.RESULT,16384)),
                'timing':timing,'finished_utc':c.now(),'activation_authorized':False,'automatic_resume_allowed':False}
        c.write_new(self.registry/RESULT,c.raw(result))
        self.lease.record_completion(result['control_events_sha256'],result['shared_result_sha256'])
        self.check_guard();self.finished=True;return result
