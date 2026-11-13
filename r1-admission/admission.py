"""Source-bound, single-attempt OFFLINE admission and supervised session evidence."""
from dataclasses import asdict
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO/'r1-session'))
import session as s
import archive as a
from capture import CaptureError, Limits, canonical, digest, exclusive_file, private_directory, strict_json
from handoff import path_without_links, read_private
from supervisor import ENVIRONMENT, RESOURCES, owner_lock, termination_handlers
import credential
import contract
from integrated_backend import line, reap

MODES = ('normal', 'cleanup-failure', 'idle', 'stall', 'tainted-diagnostic')
WALL_SECONDS = 12


def pins():
    result = s.pins()
    for path in sorted([*ROOT.iterdir(), REPO/'scripts/r1-admission-kali.sh']):
        if path.suffix in ('.py', '.md', '.sh'):
            if path.is_symlink(): raise CaptureError('admission-source-link')
            result[str(path.relative_to(REPO))] = digest(path.read_bytes())
    return dict(sorted(result.items()))


def limits(mode):
    return Limits(messages=4, seconds=1 if mode == 'idle' else 3, sample_modulus=1)


def request_row(registry, output, mode, development, attempt):
    return {'schema_version': 1, 'kind': 'r1-supervised-offline-admission-v1',
            'registry': str(registry), 'output': str(output), 'attempt_id': attempt,
            'parent_pid': os.getpid(), 'scenario': mode, 'development_endpoint': development,
            'source_sha256': pins(), 'limits': asdict(limits(mode)), 'resources': RESOURCES,
            'contract_sha256': digest(read_private(output/'registration/contract.json', 65536)),
            'live_launch_authorized': False, 'production_handoff_verified': False,
            'automatic_resume_allowed': False}


def claim_row(request, raw):
    return {'schema_version': 1, 'kind': 'r1-supervised-offline-claim-v1',
            'attempt_id': request['attempt_id'], 'request_sha256': digest(raw),
            'output': request['output']}


def load_request(output):
    output = path_without_links(output)
    raw = read_private(output/'request.json', 65536)
    row = a.row(raw)
    if (not isinstance(row, dict) or row.get('scenario') not in MODES
            or type(row.get('development_endpoint')) is not bool
            or type(row.get('parent_pid')) is not int or row['parent_pid'] <= 1
            or not isinstance(row.get('attempt_id'), str)
            or not re.fullmatch('[0-9a-f]{32}', row['attempt_id'])):
        raise CaptureError('admission-request')
    registry = path_without_links(row['registry']); private_directory(registry)
    if registry == output or registry in output.parents or output in registry.parents:
        raise CaptureError('admission-path-overlap')
    expected = request_row(registry, output, row['scenario'], row['development_endpoint'], row['attempt_id'])
    expected['parent_pid'] = row['parent_pid']
    if canonical(row) != canonical(expected): raise CaptureError('admission-request-binding')
    contract.load(output/'registration/contract.json', row['contract_sha256'])
    if read_private(registry/'claim.json', 4096) != s.json_bytes(claim_row(row, raw)):
        raise CaptureError('admission-claim-binding')
    return row, raw


def verify_evidence(output, request, request_raw):
    # Invoked only after the child exits successfully and is reaped. Recompute
    # archive/receipt/limits bindings independently; never trust exit zero alone.
    worker_raw = read_private(output/'worker-result.json', 65536)
    worker = a.row(worker_raw)
    archive = read_private(output/'export/archive.zip', a.MAX_PACKAGE)
    contents, assessment = a.verify(archive, digest(archive))
    admitted = a.row(contents['admission.json'])
    if canonical(admitted['limits']) != canonical(request['limits']):
        raise CaptureError('admission-capture-limits')
    expected_outcome = 'transport-cleanup-failed' if request['scenario'] == 'cleanup-failure' else 'capture-stopped'
    if (request['scenario'] not in ('normal', 'idle', 'cleanup-failure')
            or assessment['local_session_outcome'] != expected_outcome
            or assessment['unix_peer_uid_verified'] is not (not request['development_endpoint'])):
        raise CaptureError('admission-session-outcome')
    expected = {'schema_version': 1, 'request_sha256': digest(request_raw),
                'contract_sha256': request['contract_sha256'], 'archive_sha256': digest(archive),
                'session_admission_sha256': digest(contents['admission.json']),
                'credential_descriptor_closed': True, 'diagnostics_clean': True,
                'internet_and_dns_blocked': True, 'child_process_creation_blocked': True,
                'parent_death_sigkill': True, 'resources': RESOURCES,
                'provider_connection_opened': False, 'real_credential_used': False,
                'live_launch_authorized': False}
    if canonical(worker) != canonical(expected): raise CaptureError('admission-worker-binding')
    final, final_raw = load_request(output)
    if final_raw != request_raw or final != request: raise CaptureError('admission-changed')
    return {'archive_sha256': digest(archive), 'archive_bytes': len(archive),
            'worker_receipt_sha256': digest(worker_raw), 'assessment': assessment}


def verify_result(output, request, request_raw):
    evidence = verify_evidence(output, request, request_raw)
    restored = a.restore(output/'export/archive.zip', evidence['archive_sha256'], output/'parent-restore')
    if restored['assessment'] != evidence['assessment']:
        raise CaptureError('admission-parent-replay')
    if load_request(output)[1] != request_raw: raise CaptureError('admission-changed')
    return evidence


def node_result(mode, row):
    count = 0 if mode == 'idle' else 1
    expected = {'creations':count, 'tokens':count, 'discovery_gaps':1,
                'upstream_connections_opened':0, 'sources':[] if mode == 'idle' else ['pumpportal:create']}
    if canonical(row) != canonical(expected): raise CaptureError('admission-consumer-result')


def inspect(registry, output):
    """Read-only recovery. Does not spawn, resume, retry, or write run evidence."""
    registry, output = map(path_without_links, (registry, output))
    request, raw = load_request(output)
    if str(registry) != request['registry']: raise CaptureError('admission-recovery-registry')
    result = {'request_sha256':digest(raw), 'automatic_resume_allowed':False,
              'live_launch_authorized':False, 'reconciliation_required':True,
              'state':'admitted-outcome-unconfirmed'}
    path = output/'supervisor.json'
    if not path.exists(): return result
    row = a.row(read_private(path,65536))
    base = {'schema_version','status','request_sha256','workers_started','worker_reaped',
            'worker_returncode','consumer_reaped','automatic_resume_allowed','live_launch_authorized',
            'production_handoff_verified','provider_connection_opened','real_credential_used','development_endpoint'}
    success = row.get('status') == ('supervised-admission-development-passed-unix-pending'
        if request['development_endpoint'] else 'supervised-admission-offline-passed-live-blocked')
    fields = base | ({'evidence'} if success else {'failure_stage'})
    if 'node' in row: fields.add('node')
    if (set(row) != fields or type(row.get('schema_version')) is not int or row['schema_version'] != 1
            or row.get('request_sha256') != digest(raw)
            or row.get('development_endpoint') is not request['development_endpoint']
            or type(row.get('workers_started')) is not int or row['workers_started'] not in (0,1)
            or type(row.get('worker_reaped')) is not bool or type(row.get('consumer_reaped')) is not bool
            or (row.get('worker_returncode') is not None and type(row['worker_returncode']) is not int)
            or any(row.get(k) is not False for k in ('automatic_resume_allowed','live_launch_authorized',
                'production_handoff_verified','provider_connection_opened','real_credential_used'))):
        raise CaptureError('admission-recovery-report')
    if 'node' in row:
        if request['development_endpoint']: raise CaptureError('admission-recovery-node')
        node_result(request['scenario'], row['node'])
    if success:
        if (row['workers_started'] != 1 or not row['worker_reaped'] or not row['consumer_reaped']
                or row['worker_returncode'] != 0 or row['evidence'] != verify_evidence(output,request,raw)):
            raise CaptureError('admission-recovery-evidence')
        if not request['development_endpoint']: node_result(request['scenario'],row.get('node'))
        result.update(state='complete-offline-evidence-live-blocked', reconciliation_required=False)
    elif (row['status'] == 'supervised-admission-failed-live-blocked'
          and row['failure_stage'] in ('credential','worker-start','worker-session','independent-review')):
        result['state'] = 'failed-reconciliation-required'
    else:
        raise CaptureError('admission-recovery-status')
    return result


def run(registry, output, mode='normal', *, development=False):
    """No command, credential, provider or live argument. The input is synthetic."""
    if mode not in MODES or type(development) is not bool:
        raise CaptureError('admission-arguments')
    registry, output = path_without_links(registry), a.preflight(output)
    private_directory(registry)
    if registry == output or registry in output.parents or output in registry.parents:
        raise CaptureError('admission-path-overlap')
    with owner_lock(registry):
        # A different output path or contract cannot recover a consumed registry.
        if (registry/'claim.json').exists(): raise CaptureError('admission-already-consumed')
        output.mkdir(mode=0o700)
        (output/'registration').mkdir(mode=0o700)
        contract.freeze(output/'registration')
        request = request_row(registry, output, mode, development, uuid.uuid4().hex)
        raw = s.json_bytes(request)
        exclusive_file(output/'request.json', raw)
        exclusive_file(registry/'claim.json', s.json_bytes(claim_row(request, raw)))
        load_request(output)
        process = consumer = fd = None
        verified = None
        stage = 'credential'
        report = {'schema_version': 1, 'status': 'supervised-admission-failed-live-blocked',
                  'request_sha256': digest(raw), 'workers_started': 0,
                  'worker_reaped': False, 'worker_returncode': None, 'consumer_reaped': False,
                  'automatic_resume_allowed': False, 'live_launch_authorized': False,
                  'production_handoff_verified': False, 'provider_connection_opened': False,
                  'real_credential_used': False, 'development_endpoint': development}
        with termination_handlers():
            try:
                # Short Unix pathname and synthetic private credential input.
                # Neither the secret nor its private file path enters child argv.
                with tempfile.TemporaryDirectory(prefix='r1-admit-') as tmp:
                    directory = Path(tmp)
                    key = directory/'synthetic'; secret = ('R1-SYNTHETIC-'+uuid.uuid4().hex).encode()
                    exclusive_file(key, secret)
                    fd = credential.load_descriptor(key)
                    key.unlink()  # only our generated input, never run evidence
                    stage = 'worker-start'
                    command = [sys.executable, '-E', '-s', '-B', '-W', 'error::ResourceWarning',
                               str(ROOT/'worker.py'), str(output), str(directory), str(os.getpid()), str(fd)]
                    started = time.monotonic()
                    process = subprocess.Popen(command, cwd=output, env=ENVIRONMENT,
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        close_fds=True, pass_fds=(fd,), start_new_session=True)
                    report['workers_started'] = 1
                    os.close(fd); fd = None
                    stage = 'worker-session'
                    if not development and mode not in ('stall', 'tainted-diagnostic'):
                        deadline = time.monotonic()+3
                        while not (directory/'discovery.sock').exists():
                            if process.poll() is not None or time.monotonic() >= deadline:
                                raise CaptureError('admission-endpoint-unavailable')
                            time.sleep(0.005)
                        node = shutil.which('node')
                        if node is None: raise CaptureError('admission-node-unavailable')
                        consumer = subprocess.Popen([node, str(REPO/'r1-data/shared_scanner_fixture.mjs'),
                            'unix', str(directory/'discovery.sock')], env=ENVIRONMENT,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            close_fds=True, start_new_session=True, bufsize=0)
                        if line(consumer, 3) != b'ready\n': raise CaptureError('admission-consumer-start')
                    process.wait(timeout=max(0.001, WALL_SECONDS-(time.monotonic()-started)))
                    if process.returncode != 0: raise CaptureError('admission-worker-failed')
                    if consumer:
                        discovery = strict_json(line(consumer, 2))
                        consumer.wait(timeout=2)
                        if consumer.returncode: raise CaptureError('admission-consumer-failed')
                        node_result(mode, discovery)
                        report['node'] = discovery
                    stage = 'independent-review'
                    verified = verify_result(output, request, raw)
                    # No credential representation may persist in this run.
                    from provider_wire import secret_variants
                    variants = secret_variants(secret.decode())
                    if any(any(v in p.read_bytes() for v in variants) for p in output.rglob('*') if p.is_file()):
                        raise CaptureError('admission-secret-in-output')
            except BaseException:
                verified = None  # Fixed report only; no secret-bearing exceptions.
            finally:
                saved = {sig: signal.signal(sig, signal.SIG_IGN) for sig in (signal.SIGINT, signal.SIGTERM)}
                try:
                    if fd is not None: os.close(fd)
                    for child in (process, consumer):
                        try: reap(child)
                        except BaseException: verified = None
                    report['worker_reaped'] = process is not None and process.returncode is not None
                    report['worker_returncode'] = process.returncode if process is not None else None
                    report['consumer_reaped'] = consumer is None or consumer.returncode is not None
                finally:
                    for sig, handler in saved.items(): signal.signal(sig, handler)
        if verified is not None:
            try:
                if load_request(output)[1] != raw: raise CaptureError('admission-final-binding')
            except Exception: verified = None
        if verified is not None and report['worker_reaped'] and report['consumer_reaped']:
            report.update(status='supervised-admission-development-passed-unix-pending' if development
                          else 'supervised-admission-offline-passed-live-blocked', evidence=verified)
        else:
            report['failure_stage'] = stage
        exclusive_file(output/'supervisor.json', s.json_bytes(report))
        return report
