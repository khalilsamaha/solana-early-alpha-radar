#!/usr/bin/env python3
"""Read local backup evidence without cloud requests, credentials or configuration."""
import argparse, datetime, json, os, shutil, subprocess
from pathlib import Path
JOBS={'scanner-local':('/var/backups/solana-radar/last-run.json','solana-radar-backup.service'),
 'scanner-cloud':('/var/backups/solana-radar/cloud-last-run.json','solana-radar-backup.service'),
 'quote-ledger':('/var/backups/solana-radar-quotes/last-run.json','solana-radar-quotes-backup.service')}
BOOLS=('success','cloud_verified','localVerified','cloudVerified')
NUMBERS=('bytes','archive_bytes','archiveBytes','pruned','cloud_backups_pruned')
STATES={'running','complete','failed','local-complete','uploading','verifying','success','failure'}
def load(path,now):
 if not path.is_file():return {'status':'missing'}
 if path.is_symlink() or path.stat().st_size>65536:return {'status':'refused-input'}
 try:
  value=json.loads(path.read_text())
  if not isinstance(value,dict):raise ValueError()
 except (ValueError,OSError):return {'status':'unreadable-or-invalid'}
 out={'status':'read','statusFileAgeSeconds':max(0,round(now-path.stat().st_mtime))}
 for key in BOOLS:
  if type(value.get(key)) is bool:out[key]=value[key]
 for key in NUMBERS:
  if type(value.get(key)) is int and value[key]>=0:out[key]=value[key]
 for key in ('started_at','finished_at','startedAt','finishedAt','snapshot_at'):
  x=value.get(key)
  if isinstance(x,str) and len(x)<=40:
   try:
    dt=datetime.datetime.fromisoformat(x.replace('Z','+00:00'))
    if dt.tzinfo is not None:out[key]=dt.isoformat()
   except ValueError:pass
 if isinstance(value.get('state'),str) and value['state'] in STATES:out['state']=value['state']
 out['warningCount']=len(value['warnings']) if isinstance(value.get('warnings'),list) else None
 out['hasError']=bool(value.get('error') or value.get('errorType'))
 archive=value.get('archive')
 if isinstance(archive,str):
  a=Path(archive)
  if a.parent==path.parent and a.name.startswith('quote-') and a.name.endswith('.sqlite.gz') and not a.is_symlink() and a.is_file():out['localArchiveBytes']=a.stat().st_size
 # Never export raw errors, remote locations, configuration or healthcheck URLs.
 return out

def inventory(directory,limit=512):
 count=0;total=0;truncated=False
 if not directory.is_dir():return {'status':'missing'}
 with os.scandir(directory) as entries:
  for entry in entries:
   count+=1
   if count>limit:truncated=True;break
   if entry.is_file(follow_symlinks=False) and entry.name.endswith(('.sqlite','.sqlite.gz','.json')):total+=entry.stat(follow_symlinks=False).st_size
 disk=shutil.disk_usage(directory)
 return {'status':'read','directoryEntriesExamined':min(count,limit),'truncated':truncated,'backupAndManifestBytes':total,'diskFreeBytes':disk.free}

def service(name):
 try:
  r=subprocess.run(['systemctl','show',name,'--no-pager','-p','ActiveState','-p','SubState','-p','Result','-p','ExecMainStatus'],capture_output=True,text=True,timeout=8,check=True)
  out={}
  for line in r.stdout.splitlines():
   k,_,v=line.partition('=')
   if k in {'ActiveState','SubState','Result','ExecMainStatus'} and len(v)<=40 and all(c.isalnum() or c=='-' for c in v):out[k]=v
  return out
 except (OSError,subprocess.SubprocessError):return {'status':'unavailable'}

def build():
 now=datetime.datetime.now(datetime.timezone.utc)
 return {'version':'backup-status-1','capturedAt':now.isoformat(),'cloudRequestsMade':0,
  'jobs':{k:{'evidence':load(Path(path),now.timestamp()),'service':service(unit)} for k,(path,unit) in JOBS.items()},
  'localStorage':{k:inventory(Path(path)) for k,path in {'scanner':'/var/backups/solana-radar','quotes':'/var/backups/solana-radar-quotes'}.items()},
  'limitations':['Local status files may describe an older successful run; compare dates and service result.',
   'Cannot identify the Backblaze cap category or remaining allowance from local status. Provide the cap label, usage and limit from the Backblaze console.',
   'No backup was started, no remote file was listed or deleted, and no cap or verification setting was changed.']}
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.parse_args()
 print(json.dumps(build(),indent=2))
