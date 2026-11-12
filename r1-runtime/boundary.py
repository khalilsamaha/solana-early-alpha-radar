"""One-attempt fixed OFFLINE worker supervisor; no live mode or arbitrary command."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from capture import CaptureError, canonical, digest, exclusive_file, private_directory, sync_dir
from handoff import path_without_links
from supervisor import ENVIRONMENT, Interrupted, kill_group, owner_lock, termination_handlers
import credential

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
SCENARIOS = {'normal', 'cleanup-failure', 'credential-echo', 'stall'}
WALL_SECONDS = 12
TERM_SECONDS = 0.25
REAP_SECONDS = 1


def pins():
    # The shared fixture runs the actual capture/journal/owner/wire libraries.
    import check_shared
    paths = {str(p.relative_to(REPO)): digest(p.read_bytes()) for p in ROOT.glob('*.py')}
    paths[str((ROOT/'README.md').relative_to(REPO))] = digest((ROOT/'README.md').read_bytes())
    return {**check_shared.source_pins(), **paths}


def run(directory, credential_path, scenario='normal', *, wall_seconds=WALL_SECONDS):
    if scenario not in SCENARIOS or type(wall_seconds) not in (float, int) or not 0.05 <= wall_seconds <= WALL_SECONDS:
        raise CaptureError('runtime-arguments')
    directory = path_without_links(directory)
    private_directory(directory)
    process = fd = None
    started = time.monotonic()
    outcome, escalated = 'worker-start-failed', False
    with owner_lock(directory):
        # Persist before reading credentials or spawning. An error cannot restore
        # this allowance. Same owner directory can never automatically retry.
        manifest = {'schema_version': 1, 'mode': 'offline-runtime', 'scenario': scenario,
                    'parent_pid': os.getpid(), 'source_sha256': pins()}
        exclusive_file(directory/'attempt.json', (canonical(manifest)+'\n').encode())
        sync_dir(directory)
        with termination_handlers():
            try:
                fd = credential.load_descriptor(credential_path)
                command = [sys.executable, '-E', '-s', '-B', '-W', 'error::ResourceWarning',
                           str(ROOT/'worker_fixture.py'), str(directory), str(os.getpid()), str(fd), scenario]
                process = subprocess.Popen(command, cwd=directory, env=ENVIRONMENT,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    close_fds=True, pass_fds=(fd,), start_new_session=True)
                os.close(fd); fd = None
                try:
                    code = process.wait(timeout=max(0.001, wall_seconds-(time.monotonic()-started)))
                    outcome = 'worker-exited' if code == 0 else 'worker-failed'
                except subprocess.TimeoutExpired:
                    outcome = 'worker-deadline'
            except (Interrupted, KeyboardInterrupt):
                outcome = 'worker-interrupted'
            except Exception:
                outcome = 'worker-failed'
            finally:
                if fd is not None: os.close(fd)
                if process is not None:
                    saved = {s: signal.signal(s, signal.SIG_IGN) for s in (signal.SIGINT, signal.SIGTERM)}
                    try:
                        kill_group(process, signal.SIGTERM)
                        try:
                            process.wait(timeout=TERM_SECONDS)
                        except subprocess.TimeoutExpired:
                            escalated = True
                        finally:
                            kill_group(process, signal.SIGKILL)
                        try:
                            process.wait(timeout=REAP_SECONDS)
                        except subprocess.TimeoutExpired:
                            outcome = 'worker-cleanup-unconfirmed'
                    finally:
                        for sig, handler in saved.items(): signal.signal(sig, handler)
        report = {'schema_version':1, 'outcome':outcome, 'scenario':scenario,
                  'workers_started':int(process is not None),
                  'worker_reaped':process is not None and process.returncode is not None,
                  'forced_kill_needed':escalated, 'automatic_restart':False,
                  'elapsed_seconds':round(time.monotonic()-started,6),
                  'real_credential_used':False, 'provider_connection_opened':False,
                  'live_launch_authorized':False}
        exclusive_file(directory/'supervisor.json',(canonical(report)+'\n').encode())
        return report
