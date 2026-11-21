import copy
import unittest
import handoff_budget as budget
from test_production_control import target
from test_manifest import inputs
import admission


def fixture(stop=2):
    t=target();t['stop_seconds']=stop
    config,policy=inputs();policy.update(setup_seconds=10,service_seconds=3,shutdown_seconds=5)
    plan=admission.m.build(config,policy)
    phases={'disable_restart':30,'stop':60 if stop==35 else 30,'shared':60,'start_original':30,'restore_restart':30}
    return t,plan,phases


class BudgetTests(unittest.TestCase):
    def test_clock_and_reader_reject_forged_plan_before_use(self):
        plan=budget.build(*fixture())
        for key,value in (('schema',True),('aggregate_seconds',999),('activation_authorized',0),
                          ('original_stop_seconds',True),('shared_worker_wall_seconds',31),
                          ('target_sha256','bad'),('phase_seconds',{}),('call_allowance_lower_bounds',{})):
            changed=copy.deepcopy(plan);changed[key]=value
            with self.subTest(key=key):
                with self.assertRaises(ValueError):budget.Clock(changed)
                with self.assertRaises(ValueError):budget.validate_receipt(changed,{})

    def test_original_35_seconds_is_separate_from_shared_5_without_raising_manifest_ceiling(self):
        t,m,phases=fixture(35);p=budget.build(t,m,phases)
        self.assertEqual(p['original_stop_seconds'],35);self.assertEqual(p['shared_shutdown_seconds'],5)
        self.assertEqual(p['call_allowance_lower_bounds']['stop'],56)
        self.assertEqual(p['shared_worker_wall_seconds'],18);self.assertFalse(p['production_profile_accepted'])
        with self.assertRaisesRegex(ValueError,'shutdown-setup-ceiling'):
            admission.m.build(m['config'],{**m['policy'],'shutdown_seconds':35})

    def test_insufficient_phase_or_implicit_numeric_input_refused(self):
        t,m,phases=fixture(35)
        for key,value in [('stop',35),('shared',18),('disable_restart',True),('restore_restart',None),('stop',121)]:
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):budget.build(t,m,{**phases,key:value})
        with self.assertRaises(ValueError):budget.build(t,m,{**phases,'extra':1})

    def timer(self):
        plan=budget.build(*fixture());self.now=100.0
        return budget.Clock(plan,clock=lambda:self.now).start()

    def test_finite_phase_order_and_receipt(self):
        clock=self.timer()
        for phase in budget.PHASES:
            clock.begin(phase);self.now+=1;clock.end(phase)
        result=clock.receipt();self.assertEqual(result['elapsed_seconds'],5)
        self.assertEqual([x['phase'] for x in result['events'][::2]],list(budget.PHASES))
        self.assertFalse(result['activation_authorized'])

    def test_expiry_after_side_effect_cannot_confirm_or_retry(self):
        clock=self.timer();clock.begin('disable_restart');self.now+=30
        with self.assertRaisesRegex(ValueError,'budget-phase-expired'):clock.end('disable_restart')
        self.assertEqual(len(clock.events),1)
        with self.assertRaisesRegex(ValueError,'budget-consumed-or-closed'):clock.begin('disable_restart')

    def test_total_budget_includes_time_between_phases(self):
        clock=self.timer();clock.begin('disable_restart');clock.end('disable_restart')
        self.now+=clock.plan['aggregate_seconds']
        with self.assertRaisesRegex(ValueError,'budget-aggregate-expired'):clock.begin('stop')

    def test_clock_regression_nonfinite_and_phase_skips_refuse(self):
        for value in (99.0,float('nan'),float('inf'),True):
            clock=self.timer();self.now=value
            with self.assertRaises(ValueError):clock.check()
        clock=self.timer()
        with self.assertRaisesRegex(ValueError,'budget-phase-order'):clock.begin('shared')
        with self.assertRaises(ValueError):clock.begin('disable_restart')

    def test_incomplete_receipt_and_clock_reuse_refuse(self):
        clock=self.timer()
        with self.assertRaisesRegex(ValueError,'budget-incomplete'):clock.receipt()
        with self.assertRaisesRegex(ValueError,'budget-reuse'):clock.start()


if __name__=='__main__':unittest.main()
