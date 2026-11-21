"""Single-attempt local delivery of six previously accepted guarded handoff fixtures."""
import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "r1-data"))
from capture import CaptureError, canonical, digest, exclusive_file, private_directory, sync_dir
from handoff import path_without_links, read_private

FIRST = "90f52b9803ed0573a8efdb2c64372ed2ed52bb67"
REMAINING = "53128da5e38aecebd8f723c5bf4eb6a5a0757285"
# Content identities survive publication under different commit metadata.
READER_TREES = {
    FIRST: "6d0493c7d26862695998c6063aeefe2e9096da29",
    REMAINING: "d9124bfd401f4a7f72f9829bd8f448c6760cf570",
}
CLOSED = "closed-restored-offline-handoff-evidence"
QUARANTINE = "quarantined-handoff-evidence"


@dataclass(frozen=True)
class Fixture:
    revision: str
    size: int
    sha256: str
    verdict: str


# Accepted November 17 member indices. Only the later accepted deadline-after case is used.
FIXTURES = {
    "normal-service-exclusion": Fixture(FIRST, 403147, "3fc2abe8f8e393a42e1777ae3006c84f6517b65a935fdab181b7dec9fd2d29e9", CLOSED),
    "deadline-before-shared": Fixture(FIRST, 104388, "3e10323c55ee95be8039a12bb1f299796803cbc2ae738b389bfaa737f510db18", QUARANTINE),
    "deadline-after-shared": Fixture(REMAINING, 392125, "6b76a484926f4e0e74d9c32a42723851e7f1288dce231440c5dac12f6e60fa0c", QUARANTINE),
    "changed-application-storage": Fixture(REMAINING, 426617, "59ce449d4431ddd56cfbc43d5ff3713457f7406601a6ec8ce766e12b01c1a9ba", QUARANTINE),
    "lost-service-completion": Fixture(REMAINING, 404942, "0f2e2524b7522ee140d32a47a78c7cf634abb610f36976b95d01a97fe8e87a35", QUARANTINE),
    "service-lock-replaced": Fixture(REMAINING, 97824, "3c1d8b83ba28231b5b4ce50788016378aec03cb3ef6b71ab4dc253d61a09ed55", QUARANTINE),
}


@contextmanager
def pinned_reader(fixture):
    # The evidence reader checks producer source hashes. Run its original tree,
    # including its dependency sources, independently of later work in this checkout.
    archive = subprocess.check_output(
        ["git", "--no-replace-objects", "archive", "--format=tar", READER_TREES[fixture.revision]],
        cwd=ROOT, timeout=30,
    )
    with tempfile.TemporaryDirectory(prefix="r1b-reader-") as scratch:
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            source.extractall(scratch, filter="data")
        yield Path(scratch) / "r1-production-control/check_handoff_evidence.py"


def review(path, fixture, reader):
    raw = read_private(path, fixture.size)
    if len(raw) != fixture.size or digest(raw) != fixture.sha256:
        raise CaptureError("package-length-or-digest")
    run = subprocess.run(
        [sys.executable, "-E", "-s", "-B", str(reader), "--archive", str(path),
         "--sha256", fixture.sha256], capture_output=True, timeout=60,
    )
    expected_code = 0 if fixture.verdict == CLOSED else 2
    if run.returncode != expected_code:
        raise CaptureError("reader-verdict")
    report = json.loads(run.stdout)
    if (report["status"] != "verified-historical-offline-evidence"
            or report["sha256"] != fixture.sha256
            or report["assessment"]["classification"] != fixture.verdict
            or report["activation_authorized"] is not False):
        raise CaptureError("reader-report")
    return raw, digest(run.stdout)


def receipt(data):
    return (canonical(data) + "\n").encode()


def intent_for(fixture):
    return {"schema": 1, "scope": "guarded-local-mirror", "fixture": asdict(fixture)}


def completion_for(fixture, report_hash):
    return {
        "schema": 1, "scope": "guarded-local-mirror",
        "intent_sha256": digest(receipt(intent_for(fixture))),
        "package_sha256": fixture.sha256, "handoff_verdict": fixture.verdict,
        "reader_report_sha256": report_hash, "remote_preservation_verified": False,
        "retention_verified": False, "activation_authorized": False,
    }


def locations(root, fixture):
    root = path_without_links(root)
    private_directory(root)
    return root / ("attempt-" + fixture.sha256), root / (fixture.sha256 + ".zip")


def rehearse(root, fixture, package, reader):
    attempt, destination = locations(root, fixture)
    source = path_without_links(package)
    raw, preflight = review(source, fixture, reader)
    # The existing source and reader scratch are separate from these two new copies.
    if shutil.disk_usage(root).free < 2 * fixture.size:
        raise CaptureError("insufficient-copy-space")
    attempt.mkdir(mode=0o700)  # Exclusive durable claim, including across processes.
    sync_dir(attempt.parent)
    exclusive_file(attempt / "intent.json", receipt(intent_for(fixture)))
    exclusive_file(destination, raw)
    retrieved = attempt / "retrieved.zip"
    exclusive_file(retrieved, read_private(destination, fixture.size))
    _, restored = review(retrieved, fixture, reader)
    if (preflight != restored or read_private(destination, fixture.size) != raw
            or read_private(source, fixture.size) != raw):
        raise CaptureError("final-binding")
    completion = completion_for(fixture, restored)
    exclusive_file(attempt / "completion.json", receipt(completion))
    return completion


def inspect(root, fixture, reader):
    """Read only. A file named completion.json alone cannot finalize an attempt."""
    attempt, destination = locations(root, fixture)
    private_directory(path_without_links(attempt))
    if {p.name for p in attempt.iterdir()} != {"intent.json", "retrieved.zip", "completion.json"}:
        raise CaptureError("incomplete-attempt")
    if read_private(attempt / "intent.json", 2048) != receipt(intent_for(fixture)):
        raise CaptureError("invalid-intent")
    raw, report_hash = review(attempt / "retrieved.zip", fixture, reader)
    completion = completion_for(fixture, report_hash)
    if (read_private(destination, fixture.size) != raw
            or read_private(attempt / "completion.json", 2048) != receipt(completion)):
        raise CaptureError("invalid-completion")
    return completion


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("rehearse", "inspect"):
        command = commands.add_parser(action)
        command.add_argument("case", choices=FIXTURES)
        command.add_argument("directory", type=Path, help="existing private local mirror directory")
        if action == "rehearse":
            command.add_argument("package", type=Path, help="original private handoff/evidence.zip")
    args = parser.parse_args()
    fixture = FIXTURES[args.case]
    try:
        with pinned_reader(fixture) as reader:
            if args.action == "rehearse":
                result = rehearse(args.directory, fixture, args.package, reader)
            else:
                result = inspect(args.directory, fixture, reader)
    except (CaptureError, OSError, ValueError, KeyError, subprocess.SubprocessError, tarfile.TarError) as exc:
        reason = str(exc) if isinstance(exc, CaptureError) else type(exc).__name__
        print(canonical({"status": "unverified", "reason": reason, "activation_authorized": False}))
        return 1
    print(canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
