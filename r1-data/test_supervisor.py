import contextlib
from dataclasses import asdict
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import supervisor as s
from capture import CaptureError, canonical, digest, exclusive_file, verify


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.owner = self.root / "owner"
        self.owner.mkdir(mode=0o700)

    def tearDown(self):
        self.tmp.cleanup()

    def command(self, code):
        return [sys.executable, "-E", "-s", "-B", "-W", "error::ResourceWarning", "-c", code]

    def fixture(self, code):
        return subprocess.Popen(self.command(code), cwd=self.root, env=s.ENVIRONMENT,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, close_fds=True)

    def wait_file(self, path, process):
        until = time.monotonic() + 4
        while time.monotonic() < until:
            if path.exists():
                return
            if process.poll() is not None:
                self.fail("fixture exited before readiness")
            time.sleep(0.01)
        self.fail("fixture readiness deadline")

    def running(self, pid):
        try:
            return Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].split()[0] != "Z"
        except FileNotFoundError:
            return False

    def test_success_runs_real_child_and_preserves_bound_capture(self):
        with patch.dict(os.environ, {"PUMPPORTAL_API_KEY": "SYNTHETIC-DO-NOT-INHERIT",
                                     "HTTPS_PROXY": "SYNTHETIC-DO-NOT-INHERIT",
                                     "PYTHONPATH": "/missing/synthetic"}):
            run, report = s.rehearse(self.owner)
        self.assertEqual(report["status"], "offline-supervisor-passed-live-blocked")
        self.assertEqual(report["process"]["workers_started"], 1)
        self.assertTrue(report["process"]["worker_reaped"])
        self.assertFalse(report["network_used"])
        self.assertFalse(report["provider_connection_opened"])
        self.assertFalse(report["coexistence_accepted"])
        self.assertFalse(report["automatic_restart"])
        self.assertTrue(report["worker_receipt"]["source_preserved"])
        self.assertEqual(verify(run / "capture")["raw_rows"], 4)
        self.assertEqual((run / "capture/ticks.db").read_bytes(),
                         (run / "restore/restored/ticks.db").read_bytes())
        for path in run.rglob("*"):
            self.assertEqual(path.stat().st_mode & 0o777, 0o700 if path.is_dir() else 0o600)
            if path.is_file():
                self.assertNotIn(b"SYNTHETIC-DO-NOT-INHERIT", path.read_bytes())

    def test_owner_busy_cannot_create_run_and_lock_inode_survives(self):
        with s.owner_lock(self.owner):
            inode = (self.owner / "r1-supervisor.lock").stat().st_ino
            with self.assertRaisesRegex(CaptureError, "owner-busy"):
                s.rehearse(self.owner)
            self.assertFalse(list(self.owner.glob("run-*")))
        with s.owner_lock(self.owner):
            self.assertEqual((self.owner / "r1-supervisor.lock").stat().st_ino, inode)

    def test_unsafe_owner_alias_and_lock_are_rejected(self):
        self.owner.chmod(0o755)
        with self.assertRaises(CaptureError):
            s.rehearse(self.owner)
        self.owner.chmod(0o700)
        alias = self.root / "alias"
        alias.symlink_to(self.owner, target_is_directory=True)
        with self.assertRaises(CaptureError):
            s.rehearse(alias)
        target = self.root / "target"
        exclusive_file(target, b"preserve")
        lock = self.owner / "r1-supervisor.lock"
        lock.symlink_to(target)
        with self.assertRaises(OSError):
            s.rehearse(self.owner)
        lock.unlink()
        os.link(target, lock)
        with self.assertRaises(CaptureError):
            s.rehearse(self.owner)
        self.assertEqual(target.read_bytes(), b"preserve")

    def test_timeout_forces_unresponsive_child_and_reaps_once(self):
        code = "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)"
        started = time.monotonic()
        report = s.supervise(self.command(code), self.root, wall_seconds=0.7, term_seconds=0.1)
        self.assertEqual(report["outcome"], "worker-deadline")
        self.assertTrue(report["forced_kill_needed"])
        self.assertTrue(report["worker_reaped"])
        self.assertEqual(report["workers_started"], 1)
        self.assertLess(time.monotonic() - started, 3)

    def test_output_flood_and_exception_text_never_reach_report(self):
        code = "import os; os.write(1,b'SYNTHETIC-SECRET'*100000); os.write(2,b'SYNTHETIC-SECRET'*100000); raise RuntimeError('SYNTHETIC-SECRET')"
        with patch.object(s, "worker_command", return_value=self.command(code)):
            run, report = s.rehearse(self.owner)
        self.assertEqual(report["status"], "offline-supervisor-failed-live-blocked")
        self.assertEqual(report["process"]["outcome"], "worker-failed")
        self.assertIsNone(report["worker_receipt"])
        self.assertNotIn("SYNTHETIC-SECRET", (run / "report.json").read_text())
        self.assertEqual({p.name for p in run.iterdir()}, {"manifest.json", "report.json"})

    def test_clean_exit_without_valid_receipt_never_passes(self):
        with patch.object(s, "worker_command", return_value=self.command("pass")):
            run, report = s.rehearse(self.owner)
        self.assertEqual(report["process"]["outcome"], "worker-evidence-rejected")
        self.assertEqual(report["status"], "offline-supervisor-failed-live-blocked")
        self.assertTrue((run / "manifest.json").is_file())

    def test_changed_bundle_and_manifest_reject_receipt(self):
        run, _ = s.rehearse(self.owner)
        raw = (run / "manifest.json").read_bytes()
        bundle = run / "export/capture.zip"
        original = bundle.read_bytes()
        bundle.write_bytes(original + b"corrupt")
        with self.assertRaises(CaptureError):
            s.validate_receipt(run, raw)
        bundle.write_bytes(original)
        (run / "manifest.json").write_bytes(raw + b" ")
        with self.assertRaises(CaptureError):
            s.validate_receipt(run, raw)

    def test_receipt_symlink_oversize_and_false_flags_rejected(self):
        run, _ = s.rehearse(self.owner)
        raw = (run / "manifest.json").read_bytes()
        receipt = run / "worker-result.json"
        data = receipt.read_bytes()
        changed = json.loads(data)
        changed["source_preserved"] = False
        receipt.write_text(canonical(changed))
        with self.assertRaises(CaptureError):
            s.validate_receipt(run, raw)
        receipt.write_bytes(b" " * 16_385)
        with self.assertRaises(CaptureError):
            s.validate_receipt(run, raw)
        receipt.unlink()
        target = self.root / "receipt"
        exclusive_file(target, data)
        receipt.symlink_to(target)
        with self.assertRaises(CaptureError):
            s.validate_receipt(run, raw)

    def test_worker_rejects_manifest_source_or_mode_substitution(self):
        for field, value in (("mode", "live"), ("source_sha256", {}), ("limits", {})):
            run = self.root / ("bad-" + field)
            run.mkdir(mode=0o700)
            manifest = {"schema_version": 1, "mode": "offline-rehearsal", "run_id": run.name,
                        "parent_pid": os.getpid(), "source_sha256": s.source_pins(),
                        "limits": asdict(s.LIMITS), "resources": s.RESOURCES}
            manifest[field] = value
            exclusive_file(run / "manifest.json", canonical(manifest).encode())
            report = s.supervise(s.worker_command(run), run)
            self.assertEqual(report["outcome"], "worker-failed")
            self.assertFalse((run / "capture").exists())
            self.assertFalse((run / "worker-result.json").exists())

    def test_child_resource_limits_network_and_spawn_guards_are_real(self):
        code = f"""
import sys,os,resource,socket,subprocess,json,signal
sys.path.insert(0,{str(s.ROOT)!r})
from supervisor_worker import bootstrap
bootstrap(os.getppid())
expected=[(resource.RLIMIT_CORE,0),(resource.RLIMIT_AS,268435456),
          (resource.RLIMIT_CPU,5),(resource.RLIMIT_FSIZE,37748736),(resource.RLIMIT_NOFILE,32)]
assert all(resource.getrlimit(k)==(v,v) for k,v in expected)
assert 0 < signal.getitimer(signal.ITIMER_REAL)[0] <= 10
for call in [lambda: socket.socket(socket.AF_INET),lambda:socket.socket(socket.AF_INET6),
             lambda:socket.getaddrinfo('localhost',80),lambda:os.fork(),
             lambda:subprocess.Popen([sys.executable,'-c','pass'])]:
    try: call()
    except RuntimeError: pass
    else: raise AssertionError('guard failed')
"""
        self.assertEqual(s.supervise(self.command(code), self.root)["outcome"], "worker-exited")

    def test_parent_death_kills_bootstrapped_child(self):
        ready = self.root / "ready"
        code = f"""
import sys,os,time
sys.path.insert(0,{str(s.ROOT)!r})
from supervisor_worker import bootstrap
bootstrap(os.getppid())
from pathlib import Path
Path({str(ready)!r}).write_text(str(os.getpid()))
time.sleep(30)
"""
        parent_code = f"import subprocess; p=subprocess.Popen({self.command(code)!r}); p.wait()"
        parent = self.fixture(parent_code)
        pid = None
        try:
            self.wait_file(ready, parent)
            pid = int(ready.read_text())
            parent.kill()
            parent.wait(timeout=2)
            until = time.monotonic() + 2
            while self.running(pid) and time.monotonic() < until:
                time.sleep(0.01)
            self.assertFalse(self.running(pid))
        finally:
            if parent.poll() is None:
                parent.kill()
            parent.wait(timeout=2)
            if pid is not None and self.running(pid):
                os.kill(pid, signal.SIGKILL)

    def test_operator_interrupt_stops_child_and_restores_handler(self):
        ready, result = self.root / "ready", self.root / "result"
        child = f"import os,time; from pathlib import Path; Path({str(ready)!r}).write_text(str(os.getpid())); time.sleep(30)"
        parent_code = f"""
import sys,signal,json
from pathlib import Path
sys.path.insert(0,{str(s.ROOT)!r})
import supervisor as s
before=signal.getsignal(signal.SIGTERM)
r=s.supervise({self.command(child)!r},{str(self.root)!r})
assert signal.getsignal(signal.SIGTERM)==before
Path({str(result)!r}).write_text(json.dumps(r))
"""
        parent = self.fixture(parent_code)
        try:
            self.wait_file(ready, parent)
            pid = int(ready.read_text())
            parent.send_signal(signal.SIGTERM)
            self.assertEqual(parent.wait(timeout=3), 0)
            report = json.loads(result.read_text())
            self.assertEqual(report["outcome"], "worker-interrupted")
            self.assertTrue(report["worker_reaped"])
            self.assertFalse(self.running(pid))
        finally:
            if parent.poll() is None:
                parent.kill()
            parent.wait(timeout=2)

    def test_abrupt_exit_preserves_unclean_capture_without_repair(self):
        code = f"""
import sys,os
from pathlib import Path
sys.path.insert(0,{str(s.ROOT)!r})
from capture import Capture,Limits,canonical,digest
c=Capture(Path('capture'),Limits(messages=4,seconds=5,sample_modulus=1))
c.receive(canonical(dict(txType='create',mint='1'*31+'2',signature='2'*88)).encode())
Path('original-sha').write_text(digest(Path('capture/ticks.db').read_bytes()))
os._exit(7)
"""
        with patch.object(s, "worker_command", return_value=self.command(code)):
            run, report = s.rehearse(self.owner)
        self.assertEqual(report["status"], "offline-supervisor-failed-live-blocked")
        before = (run / "capture/ticks.db").read_bytes()
        self.assertEqual(digest(before), (run / "original-sha").read_text())
        with self.assertRaisesRegex(CaptureError, "unclean-shutdown"):
            verify(run / "capture")
        self.assertEqual(before, (run / "capture/ticks.db").read_bytes())
        self.assertFalse((run / "export").exists())
        self.assertIsNone(report["worker_receipt"])

    def test_cli_has_no_live_key_endpoint_or_budget_bypass(self):
        for option in ("--live", "--api-key", "--endpoint", "--approve-budget"):
            output = io.StringIO()
            with contextlib.redirect_stderr(output), contextlib.redirect_stdout(output):
                code = s.main(["--owner-directory", str(self.owner), "--rehearse", option, "SYNTHETIC-SECRET"])
            self.assertEqual(code, 1)
            self.assertNotIn("SYNTHETIC-SECRET", output.getvalue())
        self.assertFalse(list(self.owner.iterdir()))


if __name__ == "__main__":
    unittest.main()
