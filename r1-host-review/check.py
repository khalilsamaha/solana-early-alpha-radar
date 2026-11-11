"""Read-only production identity observation. No launcher, restart or provider I/O."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent
DOCKER = "/usr/bin/docker"
SOCKET = "/run/docker.sock"
TARGET = "solana-early-alpha-radar-radar-1"
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
FORMAT = ('{"id":{{json .Id}},"image":{{json .Image}},"pid":{{json .State.Pid}},'
          '"running":{{json .State.Running}},"started":{{json .State.StartedAt}},'
          '"health":{{if .State.Health}}{{json .State.Health.Status}}{{else}}null{{end}},'
          '"user":{{json .Config.User}},"init":{{json .HostConfig.Init}},'
          '"readonly_rootfs":{{json .HostConfig.ReadonlyRootfs}},'
          '"privileged":{{json .HostConfig.Privileged}},'
          '"userns_mode":{{json .HostConfig.UsernsMode}},'
          '"restart_policy":{{json .HostConfig.RestartPolicy.Name}}}')
FIELDS = {"id", "image", "pid", "running", "started", "health", "user", "init",
          "readonly_rootfs", "privileged", "userns_mode", "restart_policy"}


class ReviewError(Exception):
    pass


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pins():
    return {n: sha((ROOT / n).read_bytes()) for n in ("check.py", "test_check.py", "README.md")}


def strict_json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ReviewError("metadata-invalid")
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ReviewError("metadata-invalid")))


def bounded_command(command):
    """Drain no more than 16 KiB within four seconds; discard all stderr."""
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, env=ENV, start_new_session=True)
    data = bytearray()
    deadline = time.monotonic() + 4
    try:
        with selectors.DefaultSelector() as selector:
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise ReviewError("docker-timeout")
                raw = os.read(process.stdout.fileno(), 4096)
                if not raw:
                    break
                data.extend(raw)
                if len(data) > 16384:
                    raise ReviewError("docker-output-limit")
        process.wait(timeout=max(0.001, deadline - time.monotonic()))
        if process.returncode:
            raise ReviewError("docker-inspect-unavailable")
        return bytes(data)
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=1)
        process.stdout.close()


def trusted_local_docker():
    try:
        executable = Path(DOCKER).lstat()
        daemon = Path(SOCKET).lstat()
    except OSError:
        raise ReviewError("local-docker-path-unavailable") from None
    if (not stat.S_ISREG(executable.st_mode) or executable.st_uid != 0
            or executable.st_mode & 0o022 or not executable.st_mode & 0o111
            or not stat.S_ISSOCK(daemon.st_mode) or daemon.st_uid != 0):
        raise ReviewError("local-docker-path-unavailable")


def inspect(config_directory):
    raw = bounded_command([DOCKER, "--config", str(config_directory), "--host", "unix://" + SOCKET,
        "inspect", "--type", "container", "--format", FORMAT, TARGET])
    try:
        row = strict_json(raw)
        valid = (isinstance(row, dict) and set(row) == FIELDS
            and isinstance(row["id"], str) and re.fullmatch(r"[0-9a-f]{64}", row["id"])
            and isinstance(row["image"], str) and re.fullmatch(r"sha256:[0-9a-f]{64}", row["image"])
            and type(row["pid"]) is int and 0 <= row["pid"] < 2**31
            and all(type(row[k]) is bool for k in ("running", "readonly_rootfs", "privileged"))
            and (row["init"] is None or type(row["init"]) is bool)
            and row["health"] in {None, "healthy", "unhealthy", "starting"}
            and isinstance(row["started"], str) and re.fullmatch(r"[0-9TZ:.+\-]{20,40}", row["started"])
            and isinstance(row["user"], str) and re.fullmatch(r"[A-Za-z0-9_:\-]{0,65}", row["user"])
            and row["userns_mode"] in {"", "host", "private"}
            and row["restart_policy"] in {"", "no", "always", "unless-stopped", "on-failure"})
        if not valid:
            raise ReviewError("metadata-invalid")
        return row
    except Exception:
        raise ReviewError("metadata-invalid") from None


def read_proc(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise ReviewError("process-observation-unavailable") from None
    try:
        raw = bytearray()
        while True:
            part = os.read(fd, 4096)
            if not part:
                break
            raw.extend(part)
            if len(raw) > 65536:
                raise ReviewError("process-observation-unavailable")
        return raw.decode("ascii")
    finally:
        os.close(fd)


def namespace(pid):
    try:
        value = os.readlink(f"/proc/{pid}/ns/user")
    except OSError:
        raise ReviewError("process-observation-unavailable") from None
    if not re.fullmatch(r"user:\[\d+\]", value):
        raise ReviewError("process-observation-unavailable")
    return value


def process_identity(pid):
    if type(pid) is not int or not 1 <= pid < 2**31:
        raise ReviewError("process-observation-unavailable")
    fields = {}
    for line in read_proc(f"/proc/{pid}/status").splitlines():
        name, _, value = line.partition(":")
        if name in {"Uid", "Gid"}:
            if name.lower() in fields or not re.fullmatch(r"\s*\d+\s+\d+\s+\d+\s+\d+\s*", value):
                raise ReviewError("process-observation-unavailable")
            fields[name.lower()] = [int(x) for x in value.split()]
    if set(fields) != {"uid", "gid"}:
        raise ReviewError("process-observation-unavailable")
    raw_stat = read_proc(f"/proc/{pid}/stat")
    rest = raw_stat.rsplit(") ", 1)[1].split()
    start = int(rest[19])  # /proc/PID/stat field 22, after PID and parenthesized comm
    if start < 0:
        raise ReviewError("process-observation-unavailable")
    return {"pid": pid, "start_ticks": start, **fields, "user_namespace": namespace(pid)}


def children(pid):
    text = read_proc(f"/proc/{pid}/task/{pid}/children")
    if not re.fullmatch(r"(?:\d+\s*)*", text) or len(text.split()) > 16:
        raise ReviewError("process-observation-unavailable")
    result = [int(x) for x in text.split()]
    if len(set(result)) != len(result) or any(not 1 <= x < 2**31 for x in result):
        raise ReviewError("process-observation-unavailable")
    return result


def in_container(pid, container_id):
    # Bind the observed PID to the inspected container. A host Docker socket
    # mounted in another PID/cgroup namespace must not make an unrelated PID pass.
    raw = read_proc(f"/proc/{pid}/cgroup")
    return re.search(r"(?<![0-9a-f])" + re.escape(container_id) + r"(?![0-9a-f])", raw) is not None


def observe(config_directory):
    trusted_local_docker()
    first = inspect(config_directory)
    if not first["running"] or first["pid"] == 0:
        raise ReviewError("container-not-running")
    init = process_identity(first["pid"])
    child_ids = children(first["pid"]) if first["init"] else []
    if first["init"] and len(child_ids) != 1:
        raise ReviewError("container-main-process-ambiguous")
    main = process_identity(child_ids[0]) if first["init"] else init
    if not all(in_container(p, first["id"]) for p in {init["pid"], main["pid"]}):
        raise ReviewError("container-process-binding-unavailable")
    current = {"uid": os.getuid(), "effective_uid": os.geteuid(), "gid": os.getgid(),
               "effective_gid": os.getegid(), "user_namespace": namespace("self")}
    second = inspect(config_directory)
    if (first != second or process_identity(init["pid"]) != init
            or process_identity(main["pid"]) != main
            or first["init"] and children(first["pid"]) != child_ids
            or not all(in_container(p, first["id"]) for p in {init["pid"], main["pid"]})):
        raise ReviewError("container-or-process-changed")
    findings = []
    if current["uid"] == 0 or current["uid"] != current["effective_uid"]:
        findings.append("review-user-not-unprivileged")
    if main["uid"] != [current["uid"]] * 4:
        findings.append("scanner-host-uid-mismatch")
    if main["user_namespace"] != current["user_namespace"]:
        findings.append("user-namespace-mismatch")
    if first["init"] is None:
        findings.append("init-setting-unconfirmed")
    if first["health"] != "healthy":
        findings.append("container-health-not-confirmed")
    if not first["readonly_rootfs"] or first["privileged"]:
        findings.append("container-hardening-differs")
    return {"container": first, "init_process": init, "main_process": main,
            "review_user": current, "findings": findings,
            "same_uid_and_namespace_observed": not any(x in findings for x in
                ("review-user-not-unprivileged", "scanner-host-uid-mismatch", "user-namespace-mismatch")),
            "process_selection": "single-init-child" if first["init"] else "container-main-pid",
            "container_cgroup_binding_observed": True,
            "process_executable_verified": False, "production_ipc_peer_verified": False}


def run_tests():
    suite = unittest.defaultTestLoader.discover(str(ROOT), pattern="test_*.py")
    result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
    if not result.wasSuccessful() or not result.testsRun or result.skipped:
        raise ReviewError("offline-tests-failed")
    return {"run": result.testsRun, "failures": 0, "errors": 0, "skipped": 0}


def write_report(path, report):
    # Publish a complete private file exclusively; never replace existing evidence.
    raw = (json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    with tempfile.TemporaryDirectory(prefix=".r1-host-review-", dir=path.parent) as t:
        prepared = Path(t) / "report.json"
        fd = os.open(prepared, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.link(prepared, path, follow_symlinks=False)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ReviewError("arguments-invalid")


def main(argv=None):
    try:
        parser = Parser(description=__doc__)
        parser.add_argument("--output", required=True)
        parser.add_argument("--observe-local-container", action="store_true", required=True)
        args = parser.parse_args(argv)
        path = Path(args.output).absolute()
        if path.exists() or path.is_symlink() or path.parent.resolve() != path.parent:
            raise ReviewError("output-unsafe-or-existing")
        before = pins()
        started = time.monotonic()
        tests = run_tests()
        observation, error = None, None
        try:
            with tempfile.TemporaryDirectory(prefix="r1-empty-docker-config-") as tmp:
                observation = observe(Path(tmp))
        except ReviewError as exc:
            # Only these constant codes can enter a report, never daemon text.
            code = str(exc)
            allowed = {"docker-timeout", "docker-output-limit", "docker-inspect-unavailable",
                "local-docker-path-unavailable", "metadata-invalid", "process-observation-unavailable",
                "container-not-running", "container-main-process-ambiguous", "container-or-process-changed",
                "container-process-binding-unavailable"}
            error = code if code in allowed else "host-observation-unavailable"
        except Exception:
            error = "host-observation-unavailable"
        after = pins()
        if before != after:
            raise ReviewError("sources-changed")
        report = {"schema_version": 1, "status": ("host-identity-observed-rollout-blocked" if observation else
                  "host-identity-unavailable-rollout-blocked"), "tests": tests, "python": platform.python_version(),
                  "source_sha256": after, "target_container": TARGET, "observation": observation,
                  "review_wall_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "elapsed_seconds": round(time.monotonic() - started, 6),
                  "error": error, "production_modified": False, "container_exec_used": False,
                  "provider_connection_opened": False, "credentials_exported": False,
                  "funding_authorized": False, "live_launch_authorized": False, "full_gate_accepted": False}
        write_report(path, report)
        print("Read-only host identity report created; rollout remains blocked. Upload:")
        print(path)
        return 0
    except Exception:
        print("Host review stopped; no report acceptance granted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
