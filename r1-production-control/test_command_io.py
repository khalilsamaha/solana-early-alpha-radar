import json
import sys
import unittest
import command_io
import check_retained as runner


class CommandTests(unittest.TestCase):
    def invoke(self, program, **kwargs):
        return command_io.bounded([sys.executable,'-c',program],**kwargs)
    def test_stderr_warning_never_changes_successful_ack(self):
        events=[];cid='a'*64
        code="import sys;print('Flag --time has been deprecated, use --timeout instead',file=sys.stderr);print("+repr(cid)+")"
        self.assertEqual(self.invoke(code,seconds=2,cap=256,events=events),(cid+'\n').encode())
        self.assertEqual(events,[{'status':'completed','stderr_present':True}])
        # The old merged-stream runner returned warning + ID, not the exact ID.
        old=runner.image.bounded([sys.executable,'-c',code],seconds=2,cap=256)
        self.assertNotEqual(old.decode().strip(),cid)
    def test_nonzero_return_does_not_accept_stdout_ack_or_export_secret(self):
        events=[]
        with self.assertRaisesRegex(ValueError,'^command-failed$'):
            self.invoke("import sys;print('a'*64);print('private-fixture-value',file=sys.stderr);sys.exit(1)",seconds=2,events=events)
        self.assertEqual(events,[{'status':'unavailable','stderr_present':True}])
        self.assertNotIn('private-fixture-value',json.dumps(events))
    def test_independent_output_limits(self):
        for stream,error in [('stdout','command-output-limit'),('stderr','command-diagnostic-limit')]:
            with self.subTest(stream=stream),self.assertRaisesRegex(ValueError,'^'+error+'$'):
                self.invoke("import sys;print('x'*5000,file=sys."+stream+")",seconds=2,cap=256)
    def test_deadline_and_child_holding_pipe_return_unavailable(self):
        events=[]
        with self.assertRaisesRegex(ValueError,'^command-timeout$'):
            self.invoke('import time;time.sleep(3)',seconds=.1,events=events)
        self.assertEqual(events[0]['status'],'unavailable')
        with self.assertRaisesRegex(ValueError,'^command-timeout$'):
            self.invoke("import subprocess,sys;subprocess.Popen([sys.executable,'-c','import time;time.sleep(3)'])",seconds=.1)
    def test_missing_executable_and_invalid_limits_fail(self):
        events=[]
        with self.assertRaises(FileNotFoundError):
            command_io.bounded(['/no-such-r1-fixture-program'],events=events)
        self.assertEqual(events[0]['status'],'unavailable')
        for kw in ({'seconds':66},{'seconds':True},{'cap':262145},{'cap':True}):
            with self.assertRaises(ValueError):self.invoke('pass',**kw)
    def test_diagnostic_mapping_is_constant_and_never_calls_str(self):
        class Sensitive(ValueError):
            def __str__(self):raise AssertionError('must not stringify')
        self.assertEqual(runner.diagnostic(Sensitive('private-fixture-value')),'operation-unavailable')
        self.assertEqual(runner.diagnostic(ValueError('command-ack')),'command-ack')
        self.assertEqual(runner.diagnostic(PermissionError('private-fixture-value')),'permission-denied')

if __name__=='__main__':unittest.main()
