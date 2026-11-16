"""Runner fault routing with a Docker state model, not native acceptance."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import production_control as p
import check_retained as runner
from test_production_control import raw_target
c=p.c


class AttachedClient:
    def __init__(self,*args,**kwargs):
        rd,wr=os.pipe();os.write(wr,b'r1-control-ready\n');os.close(wr)
        self.stdout=os.fdopen(rd,'rb');self.pid=1
    def wait(self,timeout=None):return 0


class Engine:
    def __init__(self):self.row=None;self.isolated=None;self.calls=[];self.removed=False
    def run(self,args,**kwargs):
        self.calls.append(args)
        verb=args[1]
        if verb=='create':
            token=args[args.index('--label')+1].split('=',1)[1]
            name=args[args.index('--name')+1]
            self.row=raw_target();self.row.update(image=c.IMAGE,name='/'+name)
            self.row['config']['StopTimeout']=2
            self.isolated={'id':self.row['id'],'image':c.IMAGE,'label':token,'user':'1000:1000','network':'none',
                          'readonly':True,'privileged':False,'restart':'unless-stopped','mounts':[],
                          'running':False,'exit_code':0,'pid':0,'started':self.row['started'],
                          'finished':self.row['finished'],'memory':128*1024**2,'swap':128*1024**2,
                          'pids':32,'cpus':1000000000,'init':True,'logging':'none','caps':['ALL'],
                          'security':['no-new-privileges:true'],'cmd':c.CMD,'entrypoint':c.ENTRY}
            return (self.row['id']+'\n').encode()
        if verb=='inspect':
            if args[args.index('--format')+1]==c.FORMAT:return c.raw(self.isolated)
            return c.raw(self.row)
        if verb=='update':
            if '--memory=96m' in args:
                self.row['host']['Memory']=96*1024**2;self.isolated['memory']=96*1024**2
            else:
                value='no' if '--restart=no' in args else 'unless-stopped'
                self.row['host']['RestartPolicy']['Name']=value;self.isolated['restart']=value
        elif verb=='stop':
            self.row.update(running=False,pid=0,finished='2026-11-16T10:00:01Z')
            self.isolated.update(running=False,pid=0,finished=self.row['finished'])
        elif verb=='start':
            self.row.update(running=True,pid=101,started='2026-11-16T10:00:02Z',finished='0001-01-01T00:00:00Z')
            self.isolated.update(running=True,pid=101,started=self.row['started'],finished=self.row['finished'])
        elif verb=='rm':self.removed=True
        else:raise AssertionError(verb)
        return (self.row['id']+'\n').encode()


class RunnerTests(unittest.TestCase):
    def run_case(self,name):
        with tempfile.TemporaryDirectory() as tmp:
            engine=Engine();report={'cases':[]}
            with patch.object(runner,'run',engine.run),patch.object(runner.subprocess,'Popen',AttachedClient):
                runner.case(Path(tmp),['docker-model'],name,report)
            row=report['cases'][0]
            self.assertTrue(row['removed'] and row['client_reaped'] and engine.removed)
            self.assertEqual(p.inspect(Path(tmp)/name),row['recovery'])
            self.assertEqual(row['fault_reached'],name!='normal')
            self.assertTrue(all('solana-early-alpha-radar-radar-1' not in ' '.join(x) for x in engine.calls))
            self.assertEqual(sum(x[1]=='create' for x in engine.calls),1)
            self.assertEqual(sum(x[1]=='rm' for x in engine.calls),1)
    def test_real_failure_category_survives_cleanup(self):
        for action in ('stop','start_original','restore_restart'):
            with self.subTest(action=action),tempfile.TemporaryDirectory() as tmp:
                engine=Engine();report={'cases':[]};original=runner.Backend.mutate
                def fail(backend,operation,cid):
                    if operation==action:
                        backend.phase='dispatch-'+operation
                        raise ValueError('command-ack')
                    return original(backend,operation,cid)
                with patch.object(runner,'run',engine.run),patch.object(runner.subprocess,'Popen',AttachedClient),patch.object(runner.Backend,'mutate',fail):
                    with self.assertRaisesRegex(ValueError,'command-ack'):
                        runner.case(Path(tmp),['docker-model'],'normal',report)
                row=report['cases'][0]
                self.assertEqual(row['failure'],{'phase':'control','adapter_phase':'dispatch-'+action,'code':'command-ack'})
                self.assertTrue(row['removed'] and row['client_reaped'])
                self.assertEqual(p.inspect(Path(tmp)/'normal')['pending_action'],action)
    def test_unknown_failure_text_is_not_exported(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine=Engine();report={'cases':[]}
            with patch.object(runner,'run',engine.run),patch.object(runner.subprocess,'Popen',AttachedClient),patch.object(runner.Backend,'mutate',side_effect=ValueError('private-fixture-value')):
                with self.assertRaises(ValueError):runner.case(Path(tmp),['docker-model'],'normal',report)
            self.assertEqual(report['cases'][0]['failure']['code'],'operation-unavailable')
            self.assertNotIn('private-fixture-value',c.raw(report).decode())
    def test_normal(self):self.run_case('normal')
    def test_lost_stop(self):self.run_case('lost-stop')
    def test_lost_start(self):self.run_case('lost-start')
    def test_configuration_drift(self):self.run_case('configuration-drift')

if __name__=='__main__':unittest.main()
