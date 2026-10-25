#!/usr/bin/env python3
"""Combine local operational evidence without evaluating the frozen study."""
import argparse
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'forward-study'))
import experiment


def timestamp(value):
    if not isinstance(value, str): return None
    try:
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return int(d.timestamp()*1000) if d.tzinfo else None
    except (ValueError, OverflowError): return None


def age(value, now):
    return (now-value)/1000 if type(value) is int and 0 < value <= now else None


def intervals(windows):
    merged=[]
    for start,end in sorted(windows):
        if merged and start<=merged[-1][1]: merged[-1][1]=max(end,merged[-1][1])
        else: merged.append([start,end])
    return merged


def capture_indexes(root, source, start, now):
    """Read bounded manifests only. Requested intervals are not outcome coverage."""
    captures=root/'captures'
    if captures.resolve()!=captures or not captures.is_dir(): raise ValueError('capture-directory')
    # Bound directory traversal, including unrelated entries; never silently truncate.
    children=[]
    with os.scandir(captures) as entries:
        for entry in entries:
            if len(children)>=32: raise ValueError('directory-cap')
            children.append(entry.name)
    names=sorted(n for n in children if n.startswith('capture-'))
    if len(names)>8: raise ValueError('capture-cap')
    windows=[]; total_chunks=0
    for name in names:
        directory=captures/name
        if not re.fullmatch(r'capture-[A-Za-z0-9-]{1,80}',name) or directory.resolve()!=directory or not directory.is_dir():
            raise ValueError('capture-path')
        index=directory/'capture-index.json.gz'
        if index.resolve()!=index: raise ValueError('index-path')
        data=experiment.read_json(index,65536)
        if (data.get('format')!='quote-history-capture-1' or data.get('complete') is not True
                or data.get('sourceIdentity')!=source or data.get('windowClock')!='observer-detected-time'):
            raise ValueError('index-identity')
        a,b,c=data.get('requestedStartAt'),data.get('entryWindowEndAt'),data.get('capturedAt')
        if any(type(v) is not int for v in (a,b,c)) or not 0<a<b<=c<=now: raise ValueError('index-clock')
        chunks=data.get('chunks')
        if not isinstance(chunks,list) or not 1<=len(chunks)<=16: raise ValueError('chunks')
        cursor=a; seen=set()
        for ch in chunks:
            file=ch.get('file'); p=directory/str(file)
            if (not isinstance(file,str) or not re.fullmatch(r'part-\d{2}\.json\.gz',file) or file in seen
                    or p.resolve()!=p or not p.is_file() or not re.fullmatch(r'[0-9a-f]{64}',str(ch.get('sha256')))
                    or type(ch.get('startAt')) is not int or type(ch.get('endAt')) is not int
                    or ch['startAt']!=cursor or not cursor<ch['endAt']<=b): raise ValueError('chunk-index')
            seen.add(file); cursor=ch['endAt']
        if cursor!=b: raise ValueError('chunk-window')
        total_chunks+=len(chunks)
        if b>start: windows.append([max(a,start),b])
    merged=intervals(windows)
    gaps=[]; cursor=start
    for a,b in merged:
        if a>cursor: gaps.append([cursor,a])
        cursor=max(cursor,b)
    return {'state':'indexes-checked','captures':len(names),'chunks':total_chunks,
            'requestedWindows':merged,'gapsBeforeLastPreservedEnd':gaps,
            'lastPreservedEndAt':merged[-1][1] if merged else None,
            'preservationLagSeconds':age(merged[-1][1],now) if merged else None,
            'chunkContentsVerified':False,
            'basis':'Index identity and contiguous requested windows checked; chunk presence only. No outcomes read; intervals do not prove uptime or complete observations.'}


def study(root,now):
    try:
        _,reg=experiment.load(root,now)
        result={'state':'registration-verified','installedAt':reg['installedAt'],
                'evaluateFromAt':reg['testNotBeforeAt'],'modelEvaluated':False,'modelRefitted':False}
    except (OSError,ValueError,KeyError,TypeError): return {'state':'unavailable-or-invalid','modelEvaluated':False}
    try: result['preservation']=capture_indexes(root,reg['sourceIdentity'],reg['testNotBeforeAt'],now)
    except (OSError,ValueError,KeyError,TypeError,AttributeError,EOFError): result['preservation']={'state':'unavailable-or-invalid'}
    return result


def findings(local,health,frozen,now):
    out=[]
    def add(code,severity='warning',scope=None): out.append({'code':code,'severity':severity,**({'scope':scope} if scope else {})})
    r=health.get('readiness',{}); h=health.get('health',{})
    if r.get('state')!='read': add('readiness-unavailable')
    elif r.get('httpStatus')!=200 or r.get('ready') is not True: add('scanner-not-ready','error')
    if h.get('state')!='read': add('health-unavailable')
    else:
        if h.get('ready') is False: add('health-not-ready','error')
        for key,limit in (('lastMarketAgeSeconds',120),('lastLoopAgeSeconds',60)):
            val=h.get(key)
            if not isinstance(val,(int,float)): add('freshness-unknown',scope=key)
            elif val>limit: add('scanner-data-stale','error',key)
        if h.get('futureClockDetected'): add('scanner-clock-in-future','error')
        m=h.get('memory',{}); used=m.get('heapUsedBytes'); cap=m.get('heapLimitBytes')
        if isinstance(used,(int,float)) and isinstance(cap,(int,float)) and cap>0 and used/cap>=.8: add('heap-usage-high')
        if h.get('statistics',{}).get('hasError'): add('statistics-worker-reported-error')
        for name,p in h.get('providers',{}).items():
            if p.get('state') not in ('ok','disabled'): add('provider-not-ok',scope=name)
        n=h.get('notifications',{})
        if n.get('failed',0): add('notification-failures-recorded')
        if n.get('pending',0): add('notifications-pending','info')
    obs=local.get('observer',{})
    if obs.get('state')!='read': add('observer-metadata-unavailable')
    else:
        if obs.get('halted'): add('observer-halted','error')
        if obs.get('futurePollClock'): add('observer-clock-in-future','error')
        a=obs.get('lastPollAgeSeconds')
        if a is None: add('observer-poll-age-unknown')
        elif a>60: add('observer-poll-stale','error')
        if (obs.get('cooldownRemainingSeconds') or 0)>0: add('observer-in-cooldown')
    for key in ('scannerHostFiles','scannerContainer','observerInstallation'):
        obj=local.get(key,{})
        comparison=obj.get('files',obj)
        if comparison.get('unavailable'): add('release-files-unavailable',scope=key)
        if comparison.get('mismatched'): add('release-files-mismatch','error',key)
        if not comparison.get('expectedFiles'): add('release-comparison-unavailable',scope=key)
    installation=local.get('observerInstallation',{})
    expected=installation.get('expectedVersion')
    if expected and installation.get('configuredVersions')!=[expected]: add('observer-unit-version-mismatch','error')
    if expected and obs.get('version')!='quote-observer-'+expected: add('observer-live-version-not-confirmed')
    container=local.get('scannerContainer',{}).get('container') or {}
    if container.get('health')!='healthy': add('container-health-not-confirmed')
    if container.get('status')!='running': add('container-not-confirmed-running','error')
    if isinstance(container.get('restartCount'),int) and container['restartCount']>0: add('container-historical-restarts','info')
    units=local.get('services',{})
    for unit in ('docker.service','containerd.service','cron.service','solana-radar-quotes.service',
                 'solana-radar-research.timer','solana-radar-backup.timer','solana-radar-quotes-backup.timer'):
        if units.get(unit,{}).get('ActiveState')!='active': add('service-not-confirmed-active',scope=unit)
    backups=local.get('backups',{}).get('jobs',{})
    for name in ('scanner-local','scanner-cloud','quote-ledger'):
        e=backups.get(name,{}).get('evidence',{})
        if e.get('status')!='read': add('backup-status-unavailable',scope=name);continue
        # One failed shared service must not erase a successfully verified local stage.
        if name=='quote-ledger':
            if e.get('localVerified') is not True: add('local-quote-backup-not-verified','error')
            if e.get('cloudVerified') is not True: add('cloud-quote-backup-not-verified','error')
        elif e.get('success') is not True: add('backup-last-attempt-failed','error',name)
        if name=='scanner-cloud' and e.get('cloud_verified') is not True: add('cloud-scanner-backup-not-verified','error')
        finished=timestamp(e.get('finished_at') or e.get('finishedAt')); a=age(finished,now)
        if a is None: add('backup-finish-clock-unavailable-or-future',scope=name)
        elif a>36*3600: add('backup-status-stale',scope=name)
    d=local.get('disk',{}).get('usedPct')
    if not isinstance(d,(int,float)): add('disk-usage-unavailable')
    elif d>=85: add('disk-usage-high','error' if d>=95 else 'warning')
    if frozen.get('state')!='registration-verified': add('frozen-registration-unavailable-or-invalid','error')
    else:
        p=frozen.get('preservation',{})
        if p.get('state')!='indexes-checked': add('capture-indexes-unavailable-or-invalid','error')
        else:
            if not p.get('captures'): add('no-preserved-captures')
            if p.get('gapsBeforeLastPreservedEnd'): add('preserved-request-window-gap')
            if (p.get('preservationLagSeconds') or 0)>48*3600: add('capture-preservation-older-than-48h')
    return out


def command_json(args,timeout):
    try:
        # Children emit bounded allowlisted JSON. Raw stderr never enters public evidence.
        r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout,check=True)
        if len(r.stdout)>524288: raise ValueError('output-cap')
        value=json.loads(r.stdout)
        if not isinstance(value,dict): raise ValueError('object')
        return value
    except (OSError,ValueError,subprocess.SubprocessError): return {'state':'unavailable'}


def revision():
    try:
        sha=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],timeout=5,text=True).strip()
        if not re.fullmatch(r'[0-9a-f]{40}',sha): raise ValueError('sha')
        dirty=subprocess.run(['git','-C',str(ROOT),'diff','--quiet','HEAD','--'],timeout=5).returncode
        return {'commit':sha,'trackedChanges':dirty!=0}
    except (OSError,ValueError,subprocess.SubprocessError):return {'state':'unavailable'}


def publish(path,data):
    path=Path(path).absolute()
    if path.parent.resolve()!=path.parent or not path.parent.is_dir(): raise ValueError('output-parent')
    encoded=gzip.compress(json.dumps(data,allow_nan=False,sort_keys=True).encode())
    fd,tmp=tempfile.mkstemp(prefix='.operational-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f: f.write(encoded);f.flush();os.fsync(f.fileno())
        os.link(tmp,path)  # Never replace any existing report, including a symlink.
    finally: os.unlink(tmp)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path,required=True);p.add_argument('--experiment',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if os.geteuid()==0: p.error('Run as the project user; only the fixed local inventory helper uses sudo.')
    project=a.project.absolute();root=a.experiment.absolute()
    if project.resolve()!=project or not project.is_dir(): p.error('Project must be an existing nonsymlink directory.')
    local=command_json(['sudo','-n','python3','-E','-s',str(ROOT/'operational-review/privileged.py'),'--project',str(project)],180)
    health=command_json(['node','--env-file='+str(project/'.env'),str(ROOT/'operational-review/health.mjs')],20)
    now=time.time_ns()//1000000;frozen=study(root,now);issues=findings(local,health,frozen,now)
    result={'format':'radar-operational-review-1','capturedAt':now,'developmentSource':revision(),
            'state':'attention-required' if any(i['severity']!='info' for i in issues) else 'observed-ok',
            'local':local,'scanner':health,'frozenStudy':frozen,'findings':issues,
            'externalRequests':0,'modelEvaluated':False,'servicesChanged':False,'transactionsSent':0,
            'limitations':['Point-in-time local observations, not proof of sustained uptime or trading readiness.',
                'Requested capture windows do not prove uninterrupted data; chunk contents and outcomes are not evaluated.',
                'Backup success is local status evidence; no cloud object or recovery was checked in this run.',
                'Restart and notification counters need comparison over time; pending counts alone do not measure delivery delay.']}
    publish(a.output,result)
    print('State:',result['state'])
    for item in issues: print(item['severity']+':',item['code'],item.get('scope',''))
    print('No study evaluation, external requests or runtime changes. Upload:',a.output)


if __name__=='__main__':
    try: main()
    except (OSError,ValueError,TypeError,KeyError): sys.exit('Operational report stopped; check paths and permissions. No raw errors exported.')
