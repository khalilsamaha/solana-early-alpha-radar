"""Separate original control and shared-session clocks; no live policy approval.

Deadlines are checked around bounded calls. Filesystem/kernel scheduling stalls
are not a hard real-time guarantee; expiry consumes the attempt and never retries.
"""
import math
import re
import time
import production_control as pc
import admission
c=pc.c
PHASES=('disable_restart','stop','shared','start_original','restore_restart')
# Four 4-second inspect calls bracket each control mutation. Original stop's
# Docker command allows the declared stop timeout plus five seconds.
INSPECTION_ALLOWANCE=16
# Worker reap <=2.25s; scanner observe 4s, removal client 15s (+2s forced
# client reap), attach-client reap <=5s. Round upward and retain a reserve.
SHARED_CLEANUP_ALLOWANCE=30
SHARED_OBSERVATION_ALLOWANCE=12


def build(target,manifest,seconds):
    pc.validate(target);admission.m.validate(manifest['config'],manifest['policy'])
    policy=manifest['policy']
    c.check(all(type(policy[k]) is int for k in ('setup_seconds','service_seconds','shutdown_seconds')),'budget-shared-inputs')
    wall=sum(policy[k] for k in ('setup_seconds','service_seconds','shutdown_seconds'))
    c.check(wall<=30,'budget-offline-profile-only')
    c.check(type(seconds) is dict and set(seconds)==set(PHASES) and
            all(type(x) is int and 0<x<=120 for x in seconds.values()),'budget-phase-inputs')
    floors={phase:10+INSPECTION_ALLOWANCE for phase in PHASES}
    floors['stop']=target['stop_seconds']+5+INSPECTION_ALLOWANCE
    floors['shared']=wall+SHARED_CLEANUP_ALLOWANCE+SHARED_OBSERVATION_ALLOWANCE
    c.check(all(seconds[phase]>=floors[phase] for phase in PHASES),'budget-phase-insufficient')
    return {'schema':1,'kind':'offline-retained-handoff-budget','target_sha256':c.digest(c.raw(target)),
            'manifest_sha256':c.digest(c.raw(manifest)),'original_stop_seconds':target['stop_seconds'],
            'shared_shutdown_seconds':policy['shutdown_seconds'],'shared_worker_wall_seconds':wall,
            'phase_seconds':dict(seconds),'call_allowance_lower_bounds':floors,
            'aggregate_seconds':sum(seconds.values()),'hard_realtime_guarantee':False,
            'production_profile_accepted':False,'activation_authorized':False}


def validate_plan(plan):
    fields={'schema','kind','target_sha256','manifest_sha256','original_stop_seconds','shared_shutdown_seconds',
            'shared_worker_wall_seconds','phase_seconds','call_allowance_lower_bounds','aggregate_seconds',
            'hard_realtime_guarantee','production_profile_accepted','activation_authorized'}
    c.check(type(plan) is dict and set(plan)==fields and type(plan['schema']) is int and plan['schema']==1 and
            plan['kind']=='offline-retained-handoff-budget','budget-plan')
    c.check(all(type(plan[k]) is str and re.fullmatch('[a-f0-9]{64}',plan[k])
                for k in ('target_sha256','manifest_sha256')),'budget-plan-binding')
    c.check(all(plan[k] is False for k in ('hard_realtime_guarantee','production_profile_accepted','activation_authorized')),
            'budget-plan-authority')
    stop=plan['original_stop_seconds'];shutdown=plan['shared_shutdown_seconds'];wall=plan['shared_worker_wall_seconds']
    c.check(type(stop) is int and 1<=stop<=60 and type(shutdown) is int and type(wall) is int and
            1<=shutdown<=wall<=30,'budget-plan-durations')
    phases=plan['phase_seconds'];floors={phase:10+INSPECTION_ALLOWANCE for phase in PHASES}
    floors.update(stop=stop+5+INSPECTION_ALLOWANCE,shared=wall+SHARED_CLEANUP_ALLOWANCE+SHARED_OBSERVATION_ALLOWANCE)
    c.check(type(phases) is dict and set(phases)==set(PHASES) and
            all(type(phases[k]) is int and floors[k]<=phases[k]<=120 for k in PHASES) and
            c.raw(plan['call_allowance_lower_bounds'])==c.raw(floors) and
            type(plan['aggregate_seconds']) is int and plan['aggregate_seconds']==sum(phases.values()),'budget-plan-limits')
    return plan


class Clock:
    def __init__(self,plan,*,clock=time.monotonic):
        validate_plan(plan)
        self.plan=admission.m.parse(c.raw(plan));self.clock=clock;self.started=None;self.last=None
        self.index=0;self.active=None;self.deadline=None;self.events=[];self.poisoned=False

    def now(self):
        value=self.clock()
        c.check(type(value) in (int,float) and math.isfinite(value) and value>=0,'budget-clock')
        c.check(self.last is None or value>=self.last,'budget-clock-regressed');self.last=value
        return value

    def start(self):
        c.check(self.started is None,'budget-reuse');self.started=self.now();return self

    def check(self):
        c.check(self.started is not None and not self.poisoned,'budget-consumed-or-closed')
        try:
            now=self.now();c.check(now-self.started<self.plan['aggregate_seconds'],'budget-aggregate-expired')
            c.check(self.active is None or now<self.deadline,'budget-phase-expired')
            return now
        except BaseException:self.poisoned=True;raise

    def begin(self,phase):
        try:
            now=self.check()
            c.check(self.active is None and self.index<len(PHASES) and PHASES[self.index]==phase,'budget-phase-order')
            self.active=phase;self.deadline=min(self.started+self.plan['aggregate_seconds'],now+self.plan['phase_seconds'][phase])
            self.events.append({'phase':phase,'kind':'started','elapsed_seconds':now-self.started})
        except BaseException:self.poisoned=True;raise

    def end(self,phase):
        try:
            now=self.check();c.check(self.active==phase,'budget-phase-order')
            self.events.append({'phase':phase,'kind':'completed','elapsed_seconds':now-self.started})
            self.active=None;self.deadline=None;self.index+=1
        except BaseException:self.poisoned=True;raise

    def receipt(self):
        self.check()
        c.check(self.index==len(PHASES) and self.active is None,'budget-incomplete')
        return {'schema':1,'kind':'offline-retained-handoff-budget-complete','plan_sha256':c.digest(c.raw(self.plan)),
                'events':list(self.events),'elapsed_seconds':self.last-self.started,
                'hard_realtime_guarantee':False,'activation_authorized':False}


def validate_receipt(plan,row):
    validate_plan(plan)
    fields={'schema','kind','plan_sha256','events','elapsed_seconds','hard_realtime_guarantee','activation_authorized'}
    c.check(type(row) is dict and set(row)==fields and type(row['schema']) is int and row['schema']==1 and
            row['kind']=='offline-retained-handoff-budget-complete' and row['plan_sha256']==c.digest(c.raw(plan)) and
            row['hard_realtime_guarantee'] is False and row['activation_authorized'] is False,'budget-receipt-binding')
    events=row['events'];c.check(type(events) is list and len(events)==2*len(PHASES),'budget-event-count')
    previous=0
    for index,phase in enumerate(PHASES):
        pair=events[2*index:2*index+2]
        for event,kind in zip(pair,('started','completed')):
            c.check(type(event) is dict and set(event)=={'phase','kind','elapsed_seconds'} and
                    event['phase']==phase and event['kind']==kind,'budget-event-order')
            value=event['elapsed_seconds']
            c.check(type(value) in (int,float) and math.isfinite(value) and
                    previous<=value<plan['aggregate_seconds'],'budget-event-time');previous=value
        c.check(pair[1]['elapsed_seconds']-pair[0]['elapsed_seconds']<plan['phase_seconds'][phase],'budget-event-expired')
    elapsed=row['elapsed_seconds']
    c.check(type(elapsed) in (int,float) and math.isfinite(elapsed) and
            previous<=elapsed<plan['aggregate_seconds'],'budget-elapsed')
    return row
