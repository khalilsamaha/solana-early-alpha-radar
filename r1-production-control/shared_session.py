"""Retained-original restoration after the existing finite offline session.

Library integration, not a production launcher. Only owned synthetic scanner
sessions are supported; provider credentials and deployment remain out of scope.
Historical receipts cannot reconstruct the in-process completion witness.
"""
from pathlib import Path
import sys
import admission as a
control=a.control;c=a.c
sys.path.insert(0,str(control.ROOT/'r1-supervision'))
import manifest_supervisor as supervisor

CLAIM='retained-shared-claim.json'
INTENT='retained-shared-intent.json'
RESULT='retained-shared-result.json'


def pins():
    return {**a.pins(),**supervisor.r.pins(),
            'r1-production-control/shared_session.py':c.digest(Path(__file__).read_bytes())}


class SharedPrepared(a.Prepared):
    """One stopped original, one finite session, then explicit restoration.

    The caller keeps the returned controller open across run_shared(). Its lock
    and mutex cover the session as well as the Docker transitions. No finally
    block restores anything and no historical recovery method launches work.
    """
    def __init__(self,backend,directory,manifest_sha256,paths,*,mode='session-scanner-normal',native_development=False):
        super().__init__(backend,directory,manifest_sha256,paths)
        c.check(mode in supervisor.session.SCANNER_MODES,'shared-scanner-mode-required')
        c.check(type(native_development) is bool and
                (mode in supervisor.session.NATIVE_MODES or not native_development),'shared-native-development')
        c.check(mode!=supervisor.session.APPLICATION_MODE or not native_development,'application-native-only')
        plan,_=self.preparation()
        supervisor.session.validate_mode(plan,mode)
        self.mode=mode;self.development=native_development
        self.controller=None;self.shared_claim=None;self.attempted=False
        self.intent=None;self.completed=None;self.supervised=None;self.stop_data=None

    def open(self):
        for name in (CLAIM,INTENT,RESULT,supervisor.CLAIM,supervisor.RESULT):
            try:(self.registry/name).lstat()
            except FileNotFoundError:pass
            else:raise ValueError('shared-registry-consumed')
        self.controller=super().open()
        self.shared_claim={'schema':1,'scope':'retained-original-offline-session',
            'registry':str(self.registry),'manifest_sha256':self.sha,
            'admission_sha256':c.digest(c.raw(self.claim)),
            'mode':self.mode,'native_development':self.development,'source_sha256':pins(),
            'created_utc':c.now(),'activation_authorized':False,'automatic_resume_allowed':False}
        c.write_new(self.registry/CLAIM,c.raw(self.shared_claim))
        return self.controller

    def unchanged(self):
        c.check(self.shared_claim is not None and
                c.read(self.registry/CLAIM,262144)==c.raw(self.shared_claim) and
                self.shared_claim['source_sha256']==pins() and
                self.shared_claim['mode']==self.mode and
                self.shared_claim['native_development'] is self.development,'shared-claim-changed')
        ctrl=self.controller
        c.check(ctrl is not None and ctrl.fd is not None and not ctrl.poisoned,'shared-controller-closed')
        c.check(c.read(self.registry/'claim.json',16384)==c.raw(ctrl.claim) and
                c.read(self.registry/'events.jsonl',65536)==ctrl.data and
                (self.registry/'events.jsonl').lstat().st_ino==ctrl.inode and
                (self.registry/'lock').lstat().st_ino==ctrl.lock_inode,'shared-control-changed')
        return control.inspect(self.registry)

    def run_shared(self):
        ctrl=self.controller
        c.check(ctrl is not None and ctrl.fd is not None and not ctrl.poisoned,'shared-controller-closed')
        c.check(ctrl.mutex.acquire(blocking=False),'concurrent-operation')
        try:
            c.check(not self.attempted,'shared-attempt-consumed')
            state=self.unchanged()
            c.check(state['records']==4 and state['pending_action'] is None and
                    state['local_stop_verified'],'shared-original-not-stopped')
            self.gate('before-shared-session')
            control.before(self.backend.observe(state['target']['id']),state['target'])
            self.attempted=True;self.stop_data=ctrl.data
            self.intent={'schema':1,'claim_sha256':c.digest(c.raw(self.shared_claim)),
                'control_claim_sha256':c.digest(c.raw(ctrl.claim)),
                'control_events_sha256':c.digest(self.stop_data),'stopped_target':state['target'],
                'created_utc':c.now(),'automatic_resume_allowed':False}
            c.write_new(self.registry/INTENT,c.raw(self.intent))
            self.unchanged()
            control.before(self.backend.observe(state['target']['id']),state['target'])
            # This concrete supervisor owns, joins and reaps its worker and
            # scanner. A caller-supplied boolean or old result is never enough.
            result=supervisor.run(self.directory,self.sha,mode=self.mode,native_development=self.development)
            c.check(result['outcome']==supervisor.SUCCESS,'shared-shutdown-unconfirmed')
            c.check(supervisor.inspect(self.registry,self.sha)==result,'shared-supervision-changed')
            self.unchanged()
            control.before(self.backend.observe(state['target']['id']),state['target'])
            supervision_claim=c.read(self.registry/supervisor.CLAIM,262144)
            c.check(c.timestamp(c.parse(supervision_claim)['created_utc'])>=c.timestamp(self.intent['created_utc']),
                    'shared-supervision-precedes-intent')
            receipt={'schema':1,'scope':'retained-original-offline-session-closed',
                'intent_sha256':c.digest(c.raw(self.intent)),
                'supervision_claim_sha256':c.digest(supervision_claim),
                'supervision_result_sha256':c.digest(c.raw(result)),
                'finished_utc':c.now(),'activation_authorized':False,'automatic_resume_allowed':False,
                'provider_connection_closed':False,'billing_cutoff_verified':False}
            c.write_new(self.registry/RESULT,c.raw(receipt))
            # Set the witness only AFTER durable completion, never on inspection.
            self.completed=c.raw(receipt);self.supervised=c.raw(result)
            return result
        except BaseException:
            ctrl.poisoned=True
            raise
        finally:ctrl.mutex.release()

    def closed(self):
        state=self.unchanged()
        c.check(self.completed is not None and self.supervised is not None and self.stop_data is not None,
                'shared-shutdown-required')
        c.check(self.controller.data.startswith(self.stop_data) and
                c.read(self.registry/INTENT,16384)==c.raw(self.intent) and
                c.read(self.registry/RESULT,16384)==self.completed,'shared-completion-changed')
        receipt=c.parse(self.completed)
        c.check(c.digest(c.read(self.registry/supervisor.CLAIM,262144))==receipt['supervision_claim_sha256'] and
                c.raw(supervisor.inspect(self.registry,self.sha))==self.supervised,'shared-supervision-changed')
        return state

    def gate(self,action):
        super().gate(action)
        if action in ('start_original','restore_restart'):self.closed()

    def mutate(self,action,cid):
        self.unchanged()
        if action in ('start_original','restore_restart'):self.closed()
        return super().mutate(action,cid)
