#!/usr/bin/env python3
"""Fixed local operational reads; no raw logs, secrets, outcomes or service actions."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'deployment'))
import inventory
spec = importlib.util.spec_from_file_location('backup_status', ROOT / 'operations-tools/backup-status.py')
backup = importlib.util.module_from_spec(spec); spec.loader.exec_module(backup)
UNITS = ('docker.service','containerd.service','cron.service','solana-radar-quotes.service',
         'solana-radar-research.timer','solana-radar-backup.timer','solana-radar-quotes-backup.timer')


def read_json(path, cap=16384):
    path = Path(path)
    if path.resolve()!=path.absolute() or not path.is_file() or path.stat().st_size>cap:
        raise ValueError('unsafe-input')
    with path.open('rb') as f: raw=f.read(cap+1)
    if len(raw)>cap: raise ValueError('input-cap')
    return json.loads(raw)


def age(value, now):
    return (now-value)/1000 if type(value) is int and 0<value<=now else None


def observer(config=Path('/etc/solana-radar-quotes.json'), now=None):
    now = int(time.time()*1000) if now is None else now
    try:
        value=read_json(config); path=Path(value['reports'])/'observer.sqlite'
        if not path.is_absolute() or path.resolve()!=path or not path.is_file(): raise ValueError('ledger')
        deadline=time.monotonic()+3
        db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=1)
        try:
            db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-1024')
            db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
            db.execute('BEGIN')
            meta={}
            for k in ('lastPollAt','registeredAt','blockedUntil','halted','version'):
                row=db.execute('SELECT CASE WHEN length(CAST(v AS BLOB))<=16384 THEN v ELSE NULL END FROM meta WHERE k=?',(k,)).fetchone()
                if row and row[0] is None: raise ValueError('metadata-cap')
                meta[k]=json.loads(row[0]) if row else None
            db.rollback()
        finally: db.close()
        ver=meta['version']
        return {'state':'read','version':ver if isinstance(ver,str) and re.fullmatch(r'quote-observer-\d+\.\d+\.\d+',ver) else None,
                'lastPollAgeSeconds':age(meta['lastPollAt'],now),'registeredAgeSeconds':age(meta['registeredAt'],now),
                'futurePollClock':type(meta['lastPollAt']) is int and meta['lastPollAt']>now,
                'halted':bool(meta['halted']),
                'cooldownRemainingSeconds':max(0,(meta['blockedUntil']-now)/1000) if type(meta['blockedUntil']) is int else None,
                'basis':'Read-only metadata transaction; no signal, probe, outcome or model rows read.'}
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error):return {'state':'unavailable'}


def services():
    out={}
    for unit in UNITS:
        raw=inventory.command(['systemctl','show',unit,'--no-pager','-p','LoadState','-p','ActiveState',
                               '-p','SubState','-p','UnitFileState','-p','NRestarts'],8)
        fields={}
        for line in (raw or '').splitlines():
            k,_,v=line.partition('=')
            if k in ('LoadState','ActiveState','SubState','UnitFileState','NRestarts') and re.fullmatch(r'[a-zA-Z0-9-]{1,40}',v):fields[k]=v
        out[unit]=fields or {'status':'unavailable'}
    return out


def build(project):
    manifest=read_json(inventory.MANIFEST,131072)
    result={}
    def safe(key, fn):
        try:result[key]=fn()
        except (OSError,ValueError,TypeError,KeyError,sqlite3.Error):result[key]={'state':'unavailable'}
    safe('scannerHostFiles',lambda:inventory.disk_inventory(project,manifest))
    safe('scannerContainer',lambda:inventory.container_inventory(project,manifest['scannerFiles']))
    safe('observerInstallation',lambda:inventory.observer_inventory(manifest))
    safe('backups',backup.build)
    result['observer']=observer();result['services']=services()
    try:
        d=shutil.disk_usage(project);result['disk']={'totalBytes':d.total,'freeBytes':d.free,'usedPct':round(100*d.used/d.total,2)}
    except OSError:result['disk']={'state':'unavailable'}
    result['referenceRelease']=manifest['release']
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',type=Path,required=True);a=p.parse_args()
    try:
        if not a.project.is_absolute() or a.project.resolve()!=a.project or not a.project.is_dir():raise ValueError('project')
        print(json.dumps(build(a.project),allow_nan=False))
    except Exception:print(json.dumps({'state':'unavailable'}))
