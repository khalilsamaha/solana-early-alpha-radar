"""One consumed synthetic worker attempt bound to preparation and resource policy."""
from datetime import datetime, timezone
import math
import os
import selectors
import subprocess
import sys
import time
import runtime as r
m=r.m;p=r.preparation
ENV={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8'}
MODES={'complete','ignore-alarm','dns','process','socket','tainted-output','output-flood'}
CLAIM='supervision-claim.json'
RESULT='supervision-result.json'
SUCCESS='synthetic-worker-complete-live-blocked'
FAILURES={'worker-start-failed','worker-failed','deadline','output-limit'}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def terminal_row(claim):
    return {'schema':1,'kind':'synthetic-runtime-terminal','manifest_sha256':claim['manifest_sha256'],
            'profile':claim['profile'],'mode':claim['mode'],
            'guard_blocked':claim['mode'] in ('dns','process','socket'),
            'source_sha256':claim['source_sha256'],'production_modified':False,'provider_connection_opened':False}


def collect(process,seconds):
    data=bytearray();deadline=time.monotonic()+seconds
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout,selectors.EVENT_READ)
        while True:
            left=deadline-time.monotonic()
            if left<=0 or not selector.select(left):return None,'deadline'
            part=os.read(process.stdout.fileno(),4096)
            if not part:break
            data.extend(part)
            if len(data)>32768:return None,'output-limit'
    try:code=process.wait(timeout=max(.001,deadline-time.monotonic()))
    except subprocess.TimeoutExpired:return None,'deadline'
    return (bytes(data),'returned') if code==0 else (None,'worker-failed')


def reap(process):
    # Only this Popen child is addressed; no retained PID or external target.
    # The fixed worker rejects subprocess creation. This is not a process-tree
    # cleanup primitive for arbitrary code.
    if process.poll() is not None:return
    process.terminate()
    try:process.wait(timeout=.25)
    except subprocess.TimeoutExpired:
        process.kill()
        try:process.wait(timeout=2)
        except subprocess.TimeoutExpired:raise ValueError('runtime-reap-unconfirmed') from None


def run(manifest_directory,sha,*,mode='complete'):
    m.check(mode in MODES,'runtime-mode')
    manifest_directory=m.absolute(str(manifest_directory))
    manifest=m.inspect(manifest_directory,sha);profile=r.profile(manifest)
    registry=manifest['config']['registry_path'];m.check(registry is not None,'runtime-registry-missing')
    prepared=p.inspect(registry,sha)
    m.check(prepared['outcome']=='preparation-complete-live-blocked','runtime-preparation-required')
    fd=p.s.open_directory(registry);process=None;started=time.monotonic()
    try:
        p.same_directory(registry,fd)
        try:os.stat(RESULT,dir_fd=fd,follow_symlinks=False)
        except FileNotFoundError:pass
        else:raise ValueError('runtime-result-already-present')
        claim={'schema':1,'kind':'synthetic-manifest-runtime-attempt','registry':registry,
               'registry_identity':p.s.metadata(fd),'manifest_directory':str(manifest_directory),
               'manifest_sha256':sha,'preparation_sha256':m.digest(m.raw(prepared)),
               'profile':profile,'mode':mode,'source_sha256':r.pins(),'created_utc':stamp(),
               'activation_authorized':False,'automatic_resume_allowed':False}
        claim_bytes=p.write_at(fd,CLAIM,claim)
        outcome='worker-start-failed';terminal=None;code=None
        try:
            p.same_directory(registry,fd)
            m.check(m.inspect(manifest_directory,sha)==manifest and p.inspect(registry,sha)==prepared
                    and r.pins()==claim['source_sha256'],'runtime-input-changed')
            process=subprocess.Popen([sys.executable,'-E','-s','-B',str(r.ROOT/'worker.py'),
                str(manifest_directory),sha,str(os.getpid()),mode],stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=ENV,start_new_session=True)
            raw,outcome=collect(process,profile['wall_seconds'])
            if raw is not None:
                candidate=m.parse(raw)
                m.check(raw==m.raw(terminal_row(claim)),'runtime-terminal-binding')
                terminal=candidate;outcome=SUCCESS
        except Exception:
            outcome='worker-failed' if process is not None else 'worker-start-failed';terminal=None
        finally:
            if process is not None:
                try:reap(process);code=process.returncode
                finally:process.stdout.close()
        p.same_directory(registry,fd)
        m.check(p.read_at(fd,CLAIM)==claim_bytes and r.pins()==claim['source_sha256']
                and m.inspect(manifest_directory,sha)==manifest and p.inspect(registry,sha)==prepared,'runtime-final-binding')
        result={'schema':1,'claim_sha256':m.digest(claim_bytes),'outcome':outcome,'terminal':terminal,
                'workers_started':int(process is not None),'worker_reaped':process is not None and code is not None,
                'returncode':code,'elapsed_seconds':time.monotonic()-started,'finished_utc':stamp(),
                'activation_authorized':False,'automatic_resume_allowed':False,
                'production_modified':False,'provider_connection_opened':False}
        validate_result(result,claim,claim_bytes)
        p.write_at(fd,RESULT,result);return result
    finally:os.close(fd)


def utc(value):
    parsed=datetime.fromisoformat(value)
    m.check(parsed.utcoffset() is not None and parsed.utcoffset().total_seconds()==0,'runtime-time')
    return parsed


def validate_result(row,claim,claim_bytes):
    keys={'schema','claim_sha256','outcome','terminal','workers_started','worker_reaped','returncode',
          'elapsed_seconds','finished_utc','activation_authorized','automatic_resume_allowed',
          'production_modified','provider_connection_opened'}
    m.check(type(row) is dict and set(row)==keys and type(row['schema']) is int and row['schema']==1
            and row['claim_sha256']==m.digest(claim_bytes) and row['outcome'] in FAILURES|{SUCCESS},'runtime-result-format')
    for key in ('activation_authorized','automatic_resume_allowed','production_modified','provider_connection_opened'):
        m.check(row[key] is False,'runtime-result-authority')
    m.check(type(row['elapsed_seconds']) in (int,float) and math.isfinite(row['elapsed_seconds'])
            and row['elapsed_seconds']>=0 and utc(row['finished_utc'])>=utc(claim['created_utc']),'runtime-result-time')
    m.check(type(row['workers_started']) is int and row['workers_started'] in (0,1),'runtime-worker-count')
    if row['workers_started']==0:
        m.check(row['outcome']=='worker-start-failed' and row['worker_reaped'] is False
                and row['returncode'] is None,'runtime-start-failure')
    else:
        m.check(row['outcome']!='worker-start-failed' and row['worker_reaped'] is True
                and type(row['returncode']) is int,'runtime-reaping')
    if row['outcome']==SUCCESS:
        m.check(claim['mode'] in ('complete','dns','process','socket') and row['returncode']==0
                and m.raw(row['terminal'])==m.raw(terminal_row(claim)),'runtime-success-binding')
    else:m.check(row['terminal'] is None,'runtime-failed-terminal')


def inspect(registry,sha):
    """Historical evidence only: no worker query, signal, storage sample or write.

    Missing terminal evidence leaves reaping and worker count unknown. Neither
    recovery nor an unresolved receipt authorizes retry or indicates current life.
    """
    registry=str(m.absolute(str(registry)));fd=p.s.open_directory(registry)
    try:
        claim_bytes=p.read_at(fd,CLAIM);claim=m.parse(claim_bytes)
        keys={'schema','kind','registry','registry_identity','manifest_directory','manifest_sha256',
              'preparation_sha256','profile','mode','source_sha256','created_utc',
              'activation_authorized','automatic_resume_allowed'}
        m.check(type(claim) is dict and set(claim)==keys and m.raw(claim)==claim_bytes
                and type(claim['schema']) is int and claim['schema']==1
                and claim['kind']=='synthetic-manifest-runtime-attempt','runtime-claim-format')
        m.check(claim['registry']==registry and claim['registry_identity']==p.s.metadata(fd),'runtime-registry-binding')
        m.check(claim['manifest_sha256']==sha and claim['source_sha256']==r.pins(),'runtime-source-binding')
        m.check(claim['activation_authorized'] is False and claim['automatic_resume_allowed'] is False,'runtime-claim-authority')
        utc(claim['created_utc'])
        manifest=m.inspect(claim['manifest_directory'],sha);prepared=p.inspect(registry,sha)
        m.check(manifest['config']['registry_path']==registry and m.raw(claim['profile'])==m.raw(r.profile(manifest))
                and claim['mode'] in MODES and prepared['outcome']=='preparation-complete-live-blocked'
                and claim['preparation_sha256']==m.digest(m.raw(prepared)),'runtime-input-binding')
        try:terminal_bytes=p.read_at(fd,RESULT)
        except FileNotFoundError:
            terminal_bytes=None
            row={'schema':1,'claim_sha256':m.digest(claim_bytes),'outcome':'supervision-unresolved',
                 'workers_started':None,'worker_reaped':None,'activation_authorized':False,'automatic_resume_allowed':False}
        else:
            row=m.parse(terminal_bytes)
            m.check(m.raw(row)==terminal_bytes,'runtime-result-canonical')
            validate_result(row,claim,claim_bytes)
        p.same_directory(registry,fd)
        m.check(p.read_at(fd,CLAIM)==claim_bytes,'runtime-read-changed')
        try:after=p.read_at(fd,RESULT)
        except FileNotFoundError:after=None
        m.check(after==terminal_bytes and r.pins()==claim['source_sha256']
                and m.inspect(claim['manifest_directory'],sha)==manifest
                and p.inspect(registry,sha)==prepared,'runtime-read-changed')
        return row
    finally:os.close(fd)
