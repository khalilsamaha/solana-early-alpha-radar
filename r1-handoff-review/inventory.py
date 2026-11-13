"""Bounded read-only production inventory and blocked handoff prerequisites."""
from contextlib import redirect_stderr
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
spec = importlib.util.spec_from_file_location('handoff_host_identity', REPO/'r1-host-review/check.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
BASELINE_IMAGE = 'sha256:786529348e5b7b6563a33d8c358c3d03c97110879d6ad53af0fbae65cd0249f9'
ADMISSION_REVISION = '685d6359551c2eb69f4ccb37c06bf6424176cedf'
FORMAT = ('{"id":{{json .Id}},"image":{{json .Image}},"pid":{{json .State.Pid}},'
          '"running":{{json .State.Running}},"started":{{json .State.StartedAt}},'
          '"restart_policy":{{json .HostConfig.RestartPolicy.Name}},'
          '"memory":{{json .HostConfig.Memory}},"memory_swap":{{json .HostConfig.MemorySwap}},'
          '"pids_limit":{{json .HostConfig.PidsLimit}},"nano_cpus":{{json .HostConfig.NanoCpus}}}')
FIELDS = {'id','image','pid','running','started','restart_policy','memory','memory_swap','pids_limit','nano_cpus'}
OPEN_GATES = ('actual-direct-owner-connection-closure', 'global-registry-and-endpoint-binding',
              'production-shared-peer-and-owner-exclusivity', 'production-rollback-evidence',
              'approved-long-running-supervision-and-credential-provisioning',
              'live-retention-capacity-and-off-machine-lifecycle',
              'approved-fixed-measurement-and-numeric-exposure-terms',
              'specific-production-and-provider-activation-authority')
DIAGNOSTIC = re.compile(r'ResourceWarning|RuntimeWarning|Exception ignored|unraisable|'
    r'exception was never retrieved|exception in shielded future|was never awaited|'
    r'Task was destroyed|Exception in callback|Exception in thread|Fatal error on',re.IGNORECASE)


def canonical(row):
    return (json.dumps(row, sort_keys=True, separators=(',',':'), allow_nan=False)+'\n').encode()


def pins():
    paths = [*ROOT.glob('*.py'), *ROOT.glob('*.md'), REPO/'scripts/r1-handoff-inventory-kali.sh',
             *[REPO/'r1-host-review'/n for n in ('check.py','test_check.py','README.md')]]
    result = {}
    for path in sorted(paths):
        if path.is_symlink(): raise host.ReviewError('source-link')
        result[str(path.relative_to(REPO))] = host.sha(path.read_bytes())
    return result


def resources(config):
    row = host.strict_json(host.bounded_command([host.DOCKER,'--config',str(config),'--host','unix://'+host.SOCKET,
        'inspect','--type','container','--format',FORMAT,host.TARGET]))
    if (not isinstance(row,dict) or set(row)!=FIELDS
            or not isinstance(row['id'],str) or not re.fullmatch('[0-9a-f]{64}',row['id'])
            or not isinstance(row['image'],str) or not re.fullmatch('sha256:[0-9a-f]{64}',row['image'])
            or type(row['pid']) is not int or not 1<=row['pid']<2**31
            or row['running'] is not True
            or not isinstance(row['started'],str) or not re.fullmatch(r'[0-9TZ:.+\-]{20,40}',row['started'])
            or row['restart_policy'] not in ('','no','always','unless-stopped','on-failure')):
        raise host.ReviewError('resource-metadata-invalid')
    for key in ('memory','memory_swap','pids_limit','nano_cpus'):
        value=row[key]
        if key=='pids_limit' and value is None: continue
        if type(value) is not int or not (-1 if key in ('memory_swap','pids_limit') else 0)<=value<2**63:
            raise host.ReviewError('resource-metadata-invalid')
    return row


def memory_sample():
    values={}
    for line in host.read_proc('/proc/meminfo').splitlines():
        key,_,value=line.partition(':')
        if key in ('MemTotal','MemAvailable'):
            if key in values or not re.fullmatch(r'\s*\d+\s+kB\s*',value):
                raise host.ReviewError('memory-sample-invalid')
            values[key]=int(value.split()[0])*1024
    if set(values)!={'MemTotal','MemAvailable'} or not 0<=values['MemAvailable']<=values['MemTotal'] or not values['MemTotal']:
        raise host.ReviewError('memory-sample-invalid')
    return {'total_bytes':values['MemTotal'],'available_bytes':values['MemAvailable'],
            'scope':'review-process-proc-meminfo','allocation_or_reservation_proven':False}


def storage_sample(directory):
    info=os.statvfs(directory)
    return {'available_bytes':info.f_bavail*info.f_frsize,'total_bytes':info.f_blocks*info.f_frsize,
            'scope':'review-output-filesystem-only','production_storage_measured':False,
            'allocation_or_reservation_proven':False}


def observe(config,output_parent):
    host.trusted_local_docker()
    first=resources(config)
    identity=host.observe(config)  # two bounded identity inspections and PID/start/cgroup checks
    memory=memory_sample(); storage=storage_sample(output_parent)
    second=resources(config)
    if first!=second or any(first[k]!=identity['container'][k] for k in
                          ('id','image','pid','running','started','restart_policy')):
        raise host.ReviewError('inventory-changed')
    return {'identity':identity,'container_resource_settings':first,'memory_sample':memory,
            'storage_sample':storage,'matches_prior_offline_image':first['image']==BASELINE_IMAGE,
            'resource_settings_stable_across_reads':True,'global_connection_owner_verified':False,
            'provider_socket_closed_verified':False,'stable_registry_bound':False,
            'production_endpoint_bound':False,'credential_provisioning_verified':False}


def prerequisites(observation):
    binding=None; findings=[]
    if observation is not None:
        identity=observation['identity']
        binding={'container':identity['container'],'init_process':identity['init_process'],
                 'main_process':identity['main_process'],'review_user':identity['review_user'],
                 'container_resource_settings':observation['container_resource_settings']}
        findings=list(identity['findings'])
        if not observation['matches_prior_offline_image']: findings.append('image-differs-from-prior-offline-baseline')
    return {'schema_version':1,'status':'production-handoff-blocked','candidate_identity_binding':binding,
            'observed_findings':findings,'open_gates':list(OPEN_GATES),
            'observation_missing':observation is None,'admission_reference_revision':ADMISSION_REVISION,
            'production_actions_performed':False,'automatic_rollback_allowed':False,
            'live_launch_authorized':False,'funding_authorized':False,'full_gate_accepted':False}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def run_tests():
    stream=io.StringIO()
    suite=unittest.defaultTestLoader.discover(str(ROOT),pattern='test_*.py')
    with redirect_stderr(stream):
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    if not result.wasSuccessful() or result.skipped or not result.testsRun or DIAGNOSTIC.search(stream.getvalue()):
        raise host.ReviewError('inventory-tests-failed')
    return {'run':result.testsRun,'failures':0,'errors':0,'skipped':0},stream.getvalue().encode()


def main(argv=None):
    try:
        parser=host.Parser(description=__doc__)
        parser.add_argument('--output-directory',required=True)
        parser.add_argument('--observe-local-container',action='store_true',required=True)
        args=parser.parse_args(argv)
        output=Path(args.output_directory).absolute()
        parent=output.parent.lstat()
        if (output.exists() or output.is_symlink() or output.parent.resolve()!=output.parent
                or not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=os.getuid() or stat.S_IMODE(parent.st_mode)!=0o700):
            raise host.ReviewError('output-unsafe-or-existing')
        before=pins();tests,log=run_tests()
        output.mkdir(mode=0o700)
        started=utc_now(); clock=time.monotonic(); observation=error=None
        try:
            with tempfile.TemporaryDirectory(prefix='r1-inventory-config-') as tmp:
                observation=observe(Path(tmp),output.parent)
        except Exception as exc:
            allowed={'local-docker-path-unavailable','docker-timeout','docker-output-limit','docker-inspect-unavailable',
                     'resource-metadata-invalid','metadata-invalid','process-observation-unavailable','container-not-running',
                     'container-main-process-ambiguous','container-or-process-changed','container-process-binding-unavailable',
                     'memory-sample-invalid','inventory-changed'}
            error=str(exc) if isinstance(exc,host.ReviewError) and str(exc) in allowed else 'inventory-observation-unavailable'
        finished=utc_now()
        if pins()!=before: raise host.ReviewError('sources-changed')
        pending=prerequisites(observation)
        pending_raw=canonical(pending)
        report={'schema_version':1,'status':'handoff-inventory-observed-rollout-blocked' if observation else 'handoff-inventory-unavailable-rollout-blocked',
                'source_sha256':before,'tests':tests,'target_container':host.TARGET,'observation':observation,'error':error,
                'observation_started_utc':started,'observation_finished_utc':finished,'elapsed_seconds':round(time.monotonic()-clock,6),
                'docker_inspection_budget':4,'docker_inspection_timeout_seconds':4,'docker_output_cap_bytes':16384,
                'prerequisites_sha256':host.sha(pending_raw),'production_modified':False,'container_exec_used':False,
                'credentials_read_or_exported':False,'provider_connection_opened':False,'rpc_used':False,
                'remote_upload_performed':False,'live_launch_authorized':False,'full_gate_accepted':False}
        host.write_report(output/'prerequisites.json',pending)
        host.write_report(output/'report.json',report)
        # Offline test output contains no observed daemon/process text.
        fd=os.open(output/'validation.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as handle: handle.write(log);handle.flush();os.fsync(handle.fileno())
        print(report['status']);print(output)
        return 0
    except Exception:
        print('Inventory stopped; no rollout acceptance. Preserve any output.',file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())
