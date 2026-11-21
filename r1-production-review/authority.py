"""Bounded Docker authority metadata review; never an exclusivity or launch grant.

Only fixed local ps/inspect requests. No exec, environment, argv, mounted file,
credential, host-process or provider reads. Raw mount paths stay in memory.
"""
import argparse
import math
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import time
import zipfile
import ownership as o
i=o.i
CHUNK=2
MAX_CONTAINERS=64
SECONDS=90
FORMAT=('{"id":{{json .Id}},"image":{{json .Image}},"pid":{{json .State.Pid}},'
 '"running":{{json .State.Running}},"started":{{json .State.StartedAt}},'
 '"privileged":{{json (index .HostConfig "Privileged")}},'
 '"caps_add":{{json (index .HostConfig "CapAdd")}},'
 '"pid_mode":{{json (index .HostConfig "PidMode")}},'
 '"network_mode":{{json (index .HostConfig "NetworkMode")}},"mounts":['
 '{{range $i,$m := .Mounts}}{{if $i}},{{end}}'
 '{"type":{{json $m.Type}},"source":{{json (index $m "Source")}},"destination":{{json $m.Destination}},'
 '"rw":{{json $m.RW}},"propagation":{{json (index $m "Propagation")}}}{{end}}]}')
FIELDS={'id','image','pid','running','started','privileged','caps_add','pid_mode','network_mode','mounts'}
FLAGS=('production_modified','provider_connection_opened','activation_authorized','automatic_resume_allowed',
       'global_owner_exclusivity_verified','container_exec_used','environment_read','command_values_read',
       'mounted_file_contents_read','effective_access_verified','raw_mount_paths_exported','host_processes_inspected')
EXCLUDED=['host-users-groups-acls-and-processes','other-daemons-and-machines','provider-account-usage',
          'custom-socket-aliases-and-symlink-resolution','remote-docker-api-access','device-and-kernel-access',
          'effective-access-tests','events-between-observations-and-future-changes']
STAGES=('baseline-validation','source-before','local-docker-path','census-before','metadata-before',
        'target-binding','metadata-after','census-after','source-after')


def pins():
    result=o.pins()
    name='scripts/r1-production-authority-kali.sh';result[name]=i.digest((i.REPO/name).read_bytes())
    return result


def path(value):
    i.check(type(value) is str and i.absolute(value) and len(value)<=1024 and
            not value.startswith('//') and str(PurePosixPath(value))==value,'authority-mount-path')
    return value


def normalized(value):
    value=path(value)
    return '/run'+value[len('/var/run'):] if value=='/var/run' or value.startswith('/var/run/') else value


def contains(parent,child):
    parent=normalized(parent);child=normalized(child)
    return parent==child or parent=='/' or child.startswith(parent+'/')


def overlap(first,second):return contains(first,second) or contains(second,first)


def validate(row):
    i.check(type(row) is dict and set(row)==FIELDS,'authority-row-fields')
    i.check(type(row['id']) is str and re.fullmatch('[a-f0-9]{64}',row['id']) and
            type(row['image']) is str and re.fullmatch('sha256:[a-f0-9]{64}',row['image']),'authority-row-id')
    i.check(type(row['running']) is bool and type(row['pid']) is int and 0<=row['pid']<2**31 and
            (row['pid']>0 if row['running'] else row['pid']==0),'authority-row-state')
    i.check(i.safe_text(row['started'],40) and re.fullmatch('[0-9TZ:.+\\-]{20,40}',row['started']),
            'authority-row-started')
    i.check(type(row['privileged']) is bool,'authority-row-privileged')
    for key in ('pid_mode','network_mode'):
        i.check(type(row[key]) is str and re.fullmatch('[A-Za-z0-9_.:/-]{0,128}',row[key]),'authority-row-namespace')
    caps=[] if row['caps_add'] is None else row['caps_add']
    i.check(type(caps) is list and len(caps)<=64 and all(type(x) is str and
            re.fullmatch('(?:CAP_)?[A-Z][A-Z0-9_]{0,63}',x) for x in caps) and len(caps)==len(set(caps)),
            'authority-row-capabilities')
    mounts=row['mounts'];i.check(type(mounts) is list and len(mounts)<=32,'authority-mount-count')
    destinations=[]
    for mount in mounts:
        i.check(type(mount) is dict and set(mount)=={'type','source','destination','rw','propagation'} and
                mount['type'] in ('bind','volume','tmpfs') and type(mount['rw']) is bool,'authority-mount-fields')
        path(mount['destination']);destinations.append(mount['destination'])
        if not (mount['type']=='tmpfs' and mount['source'] in ('',None)):path(mount['source'])
        i.check(mount['propagation'] in (None,'','private','rprivate','shared','rshared','slave','rslave'),
                'authority-mount-propagation')
    i.check(len(set(destinations))==len(destinations),'authority-mount-duplicate')
    return {**row,'caps_add':sorted(caps),'mounts':sorted(mounts,key=lambda x:x['destination'])}


def project(row,data_source):
    row=validate(row);path(data_source);findings=[];mounts=[]
    if row['privileged']:findings.append('privileged-container-declared')
    if row['caps_add']:findings.append('additional-capabilities-declared')
    if row['pid_mode']=='host':findings.append('host-pid-namespace-declared')
    elif row['pid_mode']:findings.append('nondefault-pid-namespace-declared')
    if row['network_mode']=='host':findings.append('host-network-namespace-declared')
    for mount in row['mounts']:
        source=mount['source'] or '';relations=[]
        if source:
            # A read-only socket bind is still an exposure requiring review;
            # mount writability is not an API authorization observation.
            if contains(source,i.host.SOCKET):relations.append('local-docker-socket-path-exposed')
            elif PurePosixPath(source).name in ('docker.sock','containerd.sock','podman.sock'):
                relations.append('other-engine-socket-path-declared')
            if contains(mount['destination'],i.host.SOCKET):relations.append('engine-socket-destination-declared')
            if overlap(source,data_source):
                relations.append('scanner-data-write-path-declared' if mount['rw'] else 'scanner-data-read-path-declared')
            if mount['type']=='bind' and normalized(source)=='/':relations.append('host-root-bind-declared')
        if mount['propagation'] is None:relations.append('mount-propagation-unavailable')
        if mount['propagation'] in ('shared','rshared','slave','rslave'):
            relations.append('propagating-mount-declared')
        mounts.append({'type':mount['type'],'rw':mount['rw'],'propagation':mount['propagation'],
            'source_sha256':i.digest(source.encode()),'destination_sha256':i.digest(mount['destination'].encode()),
            'relations':sorted(relations)})
        findings.extend(relations)
    # Ordering here uses only digests; paths and arbitrary text never enter output.
    mounts.sort(key=lambda x:x['destination_sha256'])
    return {'container_id':row['id'],'image':row['image'],'running':row['running'],'pid':row['pid'],
            'started':row['started'],'privileged':row['privileged'],'additional_capabilities_count':len(row['caps_add']),
            'additional_capabilities_sha256':i.digest(i.raw(row['caps_add'])),
            'projection_sha256':i.digest(i.raw(row)),'mounts':mounts,'findings':sorted(set(findings))}


def census(request):
    raw=request('ps','--all','--no-trunc','--format','{{.ID}}')
    ids=raw.decode('ascii').splitlines()
    i.check(1<=len(ids)<=MAX_CONTAINERS and len(ids)==len(set(ids)) and
            all(re.fullmatch('[a-f0-9]{64}',v) for v in ids),'authority-census')
    return sorted(ids)


def inventory(request,ids):
    i.check(type(ids) is list and 1<=len(ids)<=MAX_CONTAINERS and ids==sorted(set(ids)) and
            all(type(v) is str and re.fullmatch('[a-f0-9]{64}',v) for v in ids),'authority-census')
    rows=[]
    for offset in range(0,len(ids),CHUNK):
        batch=ids[offset:offset+CHUNK]
        raw=request('inspect','--type','container','--format',FORMAT,*batch)
        parsed=[validate(i.host.strict_json(line)) for line in raw.splitlines()]
        i.check(len(parsed)==len(batch) and sorted(x['id'] for x in parsed)==batch,'authority-response-binding')
        rows.extend(parsed)
    return sorted(rows,key=lambda x:x['id'])


def target_source(rows,bound):
    old=bound['target']['metadata'];matches=[row for row in rows if row['id']==old['id']]
    i.check(len(matches)==1,'authority-target-missing');current=matches[0]
    i.check(all(current[k]==old[k] for k in ('id','image','pid','running','started')),'authority-target-generation-drift')
    old_mounts=[m for m in old['mounts'] if m['destination']=='/app/data']
    mounts=[m for m in current['mounts'] if m['destination']=='/app/data']
    i.check(len(old_mounts)==len(mounts)==1 and
            {k:mounts[0][k] for k in ('type','source','destination','rw')}==old_mounts[0],
            'authority-target-data-mount-drift')
    return path(mounts[0]['source'])


def collect(config,baseline,baseline_sha256,*,clock=time.monotonic):
    report={'schema':1,'kind':'r1-docker-authority-review','status':'docker-authority-unavailable',
            'baseline_report_sha256':baseline_sha256,'started_utc':i.stamp(),'observation_attempted':False,
            'docker_requests_attempted':0,'stages':[{'stage':name,'status':'not-run'} for name in STAGES],
            'excluded_scope':list(EXCLUDED),**{key:False for key in FLAGS}}
    active=None;started=clock();last=started
    def check_clock():
        nonlocal last
        current=clock()
        i.check(type(current) in (int,float) and type(started) in (int,float) and
                math.isfinite(current) and math.isfinite(started) and 0<=started<=last<=current and
                current-started<SECONDS,'authority-total-deadline')
        last=current
    def step(name,fn):
        nonlocal active
        active=next(s for s in report['stages'] if s['stage']==name)
        active.update(status='started',started_utc=i.stamp())
        result=fn();active.update(status='completed',finished_utc=i.stamp());return result
    def request(*args):
        check_clock()
        i.check(report['docker_requests_attempted']<66,'authority-request-bound')
        report['docker_requests_attempted']+=1
        raw=i.command(config,*args)
        check_clock()
        return raw
    try:
        def bind():
            row=i.host.strict_json(baseline)
            return o.target.bind(baseline,baseline_sha256,row['source_sha256'])
        bound=step('baseline-validation',bind)
        before=step('source-before',pins);report['source_sha256']=before
        report['observation_attempted']=True;step('local-docker-path',i.host.trusted_local_docker)
        ids=step('census-before',lambda:census(request))
        i.check(bound['target']['metadata']['id'] in ids,'authority-target-missing')
        first=step('metadata-before',lambda:inventory(request,ids))
        source=step('target-binding',lambda:target_source(first,bound))
        second=step('metadata-after',lambda:inventory(request,ids))
        i.check(first==second,'authority-metadata-changed')
        after=step('census-after',lambda:census(request));i.check(after==ids,'authority-census-changed')
        final=step('source-after',pins);i.check(final==before,'authority-source-changed')
        rows=[project(row,source) for row in first];target_id=bound['target']['metadata']['id']
        check_clock()
        report.update(status='docker-authority-observed-review-pending',workloads=rows,
            scanner_container_id=target_id,scanner_data_source_sha256=i.digest(source.encode()),
            same_projection_observed_twice=True,observed_container_count=len(rows),
            running_container_count=sum(row['running'] for row in rows),
            review_required_container_ids=[row['container_id'] for row in rows if row['container_id']!=target_id and row['findings']],
            unclassified_container_ids=[row['container_id'] for row in rows if row['container_id']!=target_id and not row['findings']],
            remaining_blockers=['docker-access-paths-require-review','host-and-other-owner-scope-unresolved',
                'effective-access-and-provider-ownership-not-proven','production-activation-not-authorized'])
    except Exception as exc:
        value=exc.args[0] if len(exc.args)==1 and type(exc.args[0]) is str else None
        # Export only literal codes owned by this module, never exception text.
        allowed={'authority-'+suffix for suffix in ('mount-path','row-fields','row-id','row-state','row-started',
            'row-privileged','row-namespace','row-capabilities','mount-count','mount-fields','mount-propagation',
            'mount-duplicate','census','response-binding','target-missing','target-generation-drift',
            'target-data-mount-drift','total-deadline','request-bound','metadata-changed','census-changed','source-changed')}
        if active:active.update(status='failed',finished_utc=i.stamp())
        report['failure']={'stage':active['stage'] if active else 'not-started','code':value if value in allowed else o.d.code(exc)}
    report['finished_utc']=i.stamp();return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-root',required=True);parser.add_argument('--baseline-sha256',required=True)
    parser.add_argument('--output',required=True);args=parser.parse_args(argv);os.umask(0o077)
    out=Path(args.output).absolute()
    i.check(not out.exists() and all(not p.is_symlink() for p in (out,*out.parents)),'authority-output-exists')
    out.mkdir(mode=0o700)
    stage='baseline-lookup'
    report={'schema':1,'kind':'r1-docker-authority-review','status':'docker-authority-unavailable',
            'started_utc':i.stamp(),'observation_attempted':False,'docker_requests_attempted':0,
            **{key:False for key in FLAGS}}
    try:
        baseline=o.find_baseline(args.baseline_root,args.baseline_sha256)
        stage='private-client-configuration'
        with tempfile.TemporaryDirectory(prefix='r1-authority-empty-config-') as config:
            stage='collection';report.update(observation_attempted=True,docker_requests_attempted=None)
            report=collect(Path(config),baseline,args.baseline_sha256)
            stage='private-client-configuration-cleanup'
    except Exception:
        for key in ('workloads','scanner_container_id','scanner_data_source_sha256','same_projection_observed_twice',
                    'observed_container_count','running_container_count','review_required_container_ids','unclassified_container_ids'):
            report.pop(key,None)
        report.update(status='docker-authority-unavailable',failure={'stage':stage,
            'code':'accepted-baseline-unavailable' if stage=='baseline-lookup' else 'observation-or-local-finalization-unavailable'})
    report['finished_utc']=i.stamp()
    i.host.write_report(out/'report.json',report)
    with zipfile.ZipFile(out/'production-authority.zip','x',compression=zipfile.ZIP_STORED) as archive:
        archive.write(out/'report.json','report.json')
    print(report['status']);print(out/'production-authority.zip')
    return 0 if report['status']=='docker-authority-observed-review-pending' else 1


if __name__=='__main__':raise SystemExit(main())
