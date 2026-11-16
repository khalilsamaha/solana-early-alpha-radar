import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import production_control as p
c = p.c


def raw_target():
    return {'id':'a'*64, 'image':'sha256:'+'b'*64, 'name':'/fixture',
            'config':{'Env':['EXAMPLE_SECRET=private-fixture-value'], 'Cmd':['node','fixture.js'],
                      'StopTimeout':35, 'StopSignal':None},
            'host':{'RestartPolicy':{'Name':'unless-stopped','MaximumRetryCount':0}, 'Memory':536870912},
            'mounts':[{'Type':'volume','Name':'fixture-data','Destination':'/app/data','RW':True}],
            'running':True,'pid':100,'started':'2026-11-16T10:00:00.000000001Z',
            'finished':'0001-01-01T00:00:00Z','exit_code':0,
            'paused':False,'restarting':False,'dead':False,'oom':False,'error':''}


def target(): return p.project(c.raw(raw_target()))


class Backend:
    def __init__(self, registry):
        self.row = target(); self.calls = []; self.registry = registry; self.lost = None; self.hook = None
    def observe(self, cid):
        if self.hook: self.hook()
        return copy.deepcopy(self.row)
    def mutate(self, action, cid):
        assert p.inspect(self.registry)['pending_action'] == action
        self.calls.append(action)
        if action == 'disable_restart': self.row['restart'] = 'no'
        elif action == 'stop': self.row.update(running=False,pid=0,finished='2026-11-16T10:00:01.000000001Z')
        elif action == 'start_original': self.row.update(running=True,pid=101,started='2026-11-16T10:00:02.000000001Z',finished='0001-01-01T00:00:00Z')
        else: self.row['restart'] = 'unless-stopped'
        if self.lost == action: raise ValueError('lost-response')
        return cid


class Tests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name); self.root.chmod(0o700); self.b = Backend(self.root)
    def control(self): return p.Control(self.root,target(),'c'*64,self.b)
    def test_complete_preserves_original_id_image_config_and_redacts_secrets(self):
        with self.control() as ctrl:
            for action in p.ACTIONS: state = ctrl.step(action)
        self.assertTrue(state['original_restored'])
        for k in ('id','image','config_sha256','restart'): self.assertEqual(state['target'][k],target()[k])
        before = {f.name:f.read_bytes() for f in self.root.iterdir()}
        self.assertEqual(p.inspect(self.root),state)
        self.assertEqual(before,{f.name:f.read_bytes() for f in self.root.iterdir()})
        self.assertNotIn(b'private-fixture-value',b''.join(before.values()))
        for k in ('automatic_resume_allowed','shared_start_authorized','production_activation_authorized','provider_connection_closed'):
            self.assertFalse(state[k])
    def test_lost_response_at_every_transition_keeps_pending_and_refuses_retry(self):
        for index, lost in enumerate(p.ACTIONS):
            with self.subTest(lost=lost), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); b=Backend(root); b.lost=lost
                with p.Control(root,target(),'c'*64,b) as ctrl:
                    for a in p.ACTIONS[:index]:ctrl.step(a)
                    with self.assertRaisesRegex(ValueError,'lost-response'):ctrl.step(lost)
                    with self.assertRaisesRegex(ValueError,'consumed-or-closed'):ctrl.step(lost)
                state=p.inspect(root);self.assertEqual(state['pending_action'],lost)
                self.assertFalse(state['original_restored']);self.assertEqual(b.calls,list(p.ACTIONS[:index+1]))
    def test_every_identity_or_configuration_drift_prevents_dispatch(self):
        changes={'pid':102,'started':'2026-11-16T10:00:03Z','image':'sha256:'+'d'*64,
                 'id':'d'*64,'config_sha256':'e'*64,'name':'/other','stop_seconds':2}
        for key, val in changes.items():
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                b=Backend(Path(tmp));b.row[key]=val
                with p.Control(tmp,target(),'c'*64,b) as ctrl:
                    with self.assertRaises(ValueError):ctrl.step('disable_restart')
                self.assertEqual(b.calls,[])
    def test_config_change_before_restore_never_starts_original(self):
        with self.control() as ctrl:
            ctrl.step('disable_restart');ctrl.step('stop');self.b.row['config_sha256']='d'*64
            with self.assertRaises(ValueError):ctrl.step('start_original')
        self.assertEqual(self.b.calls,['disable_restart','stop'])
        self.assertEqual(p.inspect(self.root)['state'],'locally-stopped')
    def test_drift_after_intent_is_pending(self):
        count=0
        def hook():
            nonlocal count
            count+=1
            if count==2:self.b.row['pid']+=1
        self.b.hook=hook
        with self.control() as ctrl:
            with self.assertRaises(ValueError):ctrl.step('disable_restart')
        self.assertEqual(self.b.calls,[]);self.assertEqual(p.inspect(self.root)['pending_action'],'disable_restart')
    def test_nonzero_stop_exit_and_unchanged_start_are_rejected(self):
        original=self.b.mutate
        def mutate(action,cid):
            result=original(action,cid)
            if action=='stop':self.b.row['exit_code']=137
            return result
        self.b.mutate=mutate
        with self.control() as ctrl:
            ctrl.step('disable_restart')
            with self.assertRaises(ValueError):ctrl.step('stop')
        self.assertEqual(p.inspect(self.root)['pending_action'],'stop')
        stopped={**target(),'running':False,'pid':0,'restart':'no','finished':'2026-11-16T10:01:00Z'}
        with self.assertRaises(ValueError):p.after('start_original',{**target(),'restart':'no'},stopped)
    def test_no_automatic_restore_and_registry_reuse(self):
        with self.control() as ctrl:ctrl.step('disable_restart');ctrl.step('stop')
        self.assertEqual(self.b.calls,['disable_restart','stop'])
        self.assertFalse(p.inspect(self.root)['automatic_resume_allowed'])
        with self.assertRaises(FileExistsError):
            with self.control():pass
    def test_original_isolated_reader_rejects_production_profile(self):
        with self.control():pass
        with self.assertRaisesRegex(ValueError,'claim-scope'):c.inspect(self.root)
    def test_production_reader_rejects_relabelled_isolated_claim(self):
        with self.control() as ctrl:
            claim=copy.deepcopy(ctrl.claim);claim['scope']='isolated-exact-target-control'
            with self.assertRaises(ValueError):p.replay(claim,b'')
    def test_secret_command_mount_resource_change_changes_projection(self):
        base=raw_target()
        for group,key,val in [('config','Env',['EXAMPLE_SECRET=changed']),('config','Cmd',['other']),
                              ('host','Memory',42)]:
            changed=copy.deepcopy(base);changed[group][key]=val
            self.assertNotEqual(p.project(c.raw(changed))['config_sha256'],target()['config_sha256'])
        base['mounts'][0]['Name']='other-volume'
        self.assertNotEqual(p.project(c.raw(base))['config_sha256'],target()['config_sha256'])
    def test_only_restart_name_is_excluded_from_config_digest(self):
        row=raw_target();row['host']['RestartPolicy']['Name']='no'
        self.assertEqual(p.project(c.raw(row))['config_sha256'],target()['config_sha256'])
        row['host']['RestartPolicy']['MaximumRetryCount']=1
        with self.assertRaises(ValueError):p.project(c.raw(row))
    def test_invalid_signals_limits_engine_states_and_json_fail_closed(self):
        for key,val in [('StopTimeout',None),('StopTimeout',0),('StopTimeout',61),('StopTimeout',True),('StopSignal','SIGKILL')]:
            row=raw_target();row['config'][key]=val
            with self.subTest(key=key,val=val),self.assertRaises(ValueError):p.project(c.raw(row))
        for key in ('paused','restarting','dead','oom'):
            row=raw_target();row[key]=True
            with self.assertRaises(ValueError):p.project(c.raw(row))
        with self.assertRaises(ValueError):p.project(b'{"id":1,"id":2}')
        with self.assertRaises(ValueError):p.project(b' '*262145)
    def test_exact_commands_use_original_id_and_35_second_timeout(self):
        calls=[]
        def run(args,**kw):calls.append((args,kw));return (target()['id']+'\n').encode()
        adapter=p.Docker(['/fixture/docker'],target(),run)
        for action in p.ACTIONS:self.assertEqual(adapter.mutate(action,target()['id']),target()['id'])
        self.assertEqual(calls[1],(['/fixture/docker','stop','--timeout','35',target()['id']],{'seconds':40,'cap':256}))
        self.assertEqual(calls[2][0],['/fixture/docker','start',target()['id']])
        with self.assertRaises(ValueError):adapter.mutate('stop','e'*64)
        with self.assertRaises(ValueError):adapter.mutate('rm',target()['id'])
    def test_fsync_failure_never_dispatches(self):
        with self.control() as ctrl:
            with patch.object(c.os,'fsync',side_effect=OSError('fixture')):
                with self.assertRaises(OSError):ctrl.step('disable_restart')
        self.assertEqual(self.b.calls,[])
    def test_wrong_ack_keeps_intent(self):
        self.b.mutate=lambda action,cid:'wrong'
        with self.control() as ctrl:
            with self.assertRaisesRegex(ValueError,'command-ack'):ctrl.step('disable_restart')
        self.assertEqual(p.inspect(self.root)['pending_action'],'disable_restart')
    def test_torn_log_and_rehashed_authority_rejected(self):
        with self.control() as ctrl:ctrl.step('disable_restart')
        file=self.root/'events.jsonl';data=file.read_bytes();rows=[c.parse(x) for x in data.splitlines()]
        rows[1]['receipt']['provider_connection_closed']=True
        rows[1]['hash']=c.digest(c.raw({k:v for k,v in rows[1].items() if k!='hash'}))
        file.write_bytes(b''.join(c.raw(x) for x in rows))
        with self.assertRaises(ValueError):p.inspect(self.root)
        file.write_bytes(data+b'{')
        with self.assertRaises(ValueError):p.inspect(self.root)
    def test_all_interruption_prefixes_replay_without_operations(self):
        with self.control() as ctrl:
            for action in p.ACTIONS:ctrl.step(action)
            claim=copy.deepcopy(ctrl.claim);lines=ctrl.data.splitlines(keepends=True)
        for n in range(9):
            state=p.replay(claim,b''.join(lines[:n]))
            self.assertEqual(state['records'],n)
            self.assertEqual(state['pending_action'],p.ACTIONS[n//2] if n%2 else None)
            self.assertEqual(state['original_restored'],n==8)
        self.assertEqual(len(self.b.calls),4)

if __name__=='__main__':unittest.main()
