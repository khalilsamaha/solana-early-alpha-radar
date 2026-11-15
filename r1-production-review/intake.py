"""Bounded read-only production metadata intake. No activation or mutation API."""
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import time
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parent
spec=importlib.util.spec_from_file_location('production_host_identity',REPO/'r1-host-review/check.py')
host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
PROJECT='solana-early-alpha-radar';SERVICE='radar'
FORMAT=('{'+'"id":{{json .Id}},"image":{{json .Image}},"name":{{json .Name}},'
 '"pid":{{json .State.Pid}},"running":{{json .State.Running}},"started":{{json .State.StartedAt}},'
 '"user":{{json .Config.User}},"working_dir":{{json .Config.WorkingDir}},'
 '"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
 '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
 '"readonly_rootfs":{{json .HostConfig.ReadonlyRootfs}},"privileged":{{json .HostConfig.Privileged}},'
 '"init":{{json .HostConfig.Init}},"restart_policy":{{json .HostConfig.RestartPolicy.Name}},'
 '"memory":{{json .HostConfig.Memory}},"memory_swap":{{json .HostConfig.MemorySwap}},'
 '"nano_cpus":{{json .HostConfig.NanoCpus}},"pids_limit":{{json .HostConfig.PidsLimit}},'
 '"network_mode":{{json .HostConfig.NetworkMode}},"mounts":['
 '{{range $i,$m := .Mounts}}{{if $i}},{{end}}'
 '{"type":{{json $m.Type}},"source":{{json $m.Source}},"destination":{{json $m.Destination}},"rw":{{json $m.RW}}}{{end}}]}')
FIELDS={'id','image','name','pid','running','started','user','working_dir','project','service','readonly_rootfs',
        'privileged','init','restart_policy','memory','memory_swap','nano_cpus','pids_limit','network_mode','mounts'}


def raw(row):return (json.dumps(row,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def digest(data):return hashlib.sha256(data).hexdigest()
def check(value,code):
    if not value:raise ValueError(code)
def stamp():return datetime.now(timezone.utc).isoformat()


def pins():
    result={str((Path('r1-host-review')/name)):value for name,value in host.pins().items()}
    for path in [*sorted(ROOT.glob('*.py')),*sorted(ROOT.glob('*.md')),REPO/'scripts/r1-production-context-kali.sh']:
        check(not path.is_symlink(),'source-link');result[str(path.relative_to(REPO))]=digest(path.read_bytes())
    return result


def safe_text(value,bound=1024):
    return isinstance(value,str) and len(value)<=bound and all(ord(ch)>=32 and ord(ch)!=127 for ch in value)


def absolute(value):
    return safe_text(value) and value.startswith('/') and str(Path(value))==value and '..' not in Path(value).parts


def validate(row):
    check(type(row) is dict and set(row)==FIELDS,'context-fields')
    check(isinstance(row['id'],str) and re.fullmatch('[a-f0-9]{64}',row['id'])
          and isinstance(row['image'],str) and re.fullmatch('sha256:[a-f0-9]{64}',row['image']),'context-identity')
    check(row['name']=='/'+host.TARGET and row['project']==PROJECT and row['service']==SERVICE,'context-target')
    check(type(row['pid']) is int and 0<=row['pid']<2**31 and type(row['running']) is bool,'context-state')
    check(safe_text(row['started'],40) and re.fullmatch(r'[0-9TZ:.+\-]{20,40}',row['started']),'context-started')
    for key in ('readonly_rootfs','privileged'):check(type(row[key]) is bool,'context-boolean')
    check(row['init'] is None or type(row['init']) is bool,'context-init')
    check(safe_text(row['user'],65) and re.fullmatch(r'[A-Za-z0-9_:\-]*',row['user']),'context-user')
    check(row['working_dir']=='' or absolute(row['working_dir']),'context-working-directory')
    check(row['restart_policy'] in ('','no','always','unless-stopped','on-failure'),'context-restart')
    for key in ('memory','nano_cpus'):
        check(type(row[key]) is int and 0<=row[key]<=2**63-1,'context-resource')
    check(type(row['memory_swap']) is int and -1<=row['memory_swap']<=2**63-1,'context-swap')
    check(row['pids_limit'] is None or type(row['pids_limit']) is int and -1<=row['pids_limit']<=2**31-1,'context-pids')
    check(safe_text(row['network_mode'],128) and re.fullmatch(r'[A-Za-z0-9_.:\-]{0,128}',row['network_mode']),'context-network')
    check(type(row['mounts']) is list and len(row['mounts'])<=16,'context-mount-count')
    destinations=[]
    for mount in row['mounts']:
        check(type(mount) is dict and set(mount)=={'type','source','destination','rw'}
              and mount['type'] in ('bind','volume','tmpfs') and type(mount['rw']) is bool,'context-mount-fields')
        check(absolute(mount['destination']) and (absolute(mount['source']) or mount['type']=='tmpfs' and mount['source']==''),'context-mount-path')
        destinations.append(mount['destination'])
    check(len(destinations)==len(set(destinations)),'context-mount-alias')
    return row


def command(config,*args):
    return host.bounded_command([host.DOCKER,'--config',str(config),'--host','unix://'+host.SOCKET,*args])


def metadata(config):
    return validate(host.strict_json(command(config,'inspect','--type','container','--format',FORMAT,host.TARGET)))


def census(config):
    data=command(config,'ps','--no-trunc','--filter','label=com.docker.compose.project='+PROJECT,'--format','{{.ID}}')
    rows=data.decode('ascii').splitlines()
    check(len(rows)<=16 and len(rows)==len(set(rows)) and all(re.fullmatch('[a-f0-9]{64}',row) for row in rows),'context-census')
    return sorted(rows)


def observe(config):
    """One bounded pass: two metadata/census samples around the established identity check.

    Only fixed Docker inspect/ps requests and the existing bounded /proc identity
    reads are issued. No argv, environment, executable, mount contents or sockets
    are read, and no in-container process is launched.
    """
    before=pins();started=stamp();clock=time.monotonic()
    host.trusted_local_docker()
    first=metadata(config);members=census(config)
    identity=host.observe(config)
    second=metadata(config);after=census(config)
    check(first==second and members==after,'context-changed')
    check(first['id'] in members,'context-target-outside-census')
    check(all(first[key]==identity['container'][key] for key in
          ('id','image','pid','running','started','user','readonly_rootfs','privileged','init','restart_policy')),'context-process-binding')
    check(first['running'] is True and first['pid']>0,'context-not-running')
    check(pins()==before,'context-source-changed')
    return {'schema':1,'kind':'read-only-production-context','target':host.TARGET,
            'started_utc':started,'finished_utc':stamp(),'elapsed_seconds':time.monotonic()-clock,
            'source_sha256':before,'metadata':first,'metadata_sha256':digest(raw(first)),
            'project_running_container_ids':members,'project_running_container_count':len(members),
            'identity_observation':identity,'same_projection_observed_twice':True,
            'sole_owner_verified':False,'full_configuration_verified':False,'production_ipc_peer_verified':False,
            'environment_read':False,'argv_read':False,'mounted_file_contents_read':False,
            'filesystem_capacity_observed':False,'container_exec_used':False,'production_modified':False,
            'provider_connection_opened':False,'activation_authorized':False,'automatic_resume_allowed':False,
            'remaining_blockers':['full-scanner-configuration-not-reviewed','global-owner-exclusivity-not-proven',
                'production-ipc-peer-not-observed','registry-capture-and-retention-plan-unapproved',
                'live-credentials-resources-and-pilot-terms-unapproved']}
