#!/usr/bin/env python3
"""Run one bounded metadata-only statistics profile inside the existing radar container."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from operational import publish

ROOT=Path(__file__).resolve().parents[1]


def collect(project, runner=subprocess.run, projected=False):
    manifest=json.loads((ROOT/'deployment/engineering-release-1.json').read_text())
    hashes={k:v for k,v in manifest['scannerFiles'].items() if k.startswith('src/') and k.endswith('.js')}
    script=(ROOT/'operational-review/stats-profile.mjs').read_bytes()
    command=['sudo','-n','docker','compose','--project-directory',str(project),
             'exec','-T','radar','node','--input-type=module','-',json.dumps(hashes,separators=(',',':'))]
    if projected:
        candidate=(ROOT/'statistics-lab/projected-reader.mjs').read_bytes()
        if len(candidate)>16384:raise ValueError('projection-cap')
        command.append(base64.b64encode(candidate).decode('ascii'))
    try:
        r=runner(command,input=script,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=20)
        if r.returncode!=0 or len(r.stdout)>65536:raise ValueError('profile-command')
        result=json.loads(r.stdout)
        if not isinstance(result,dict) or result.get('format')!='statistics-profile-1':raise ValueError('profile-format')
        # The reviewed script emits only operational fields, never computed statistics.
        return result
    except (OSError,ValueError,subprocess.SubprocessError):
        return {'format':'statistics-profile-1','state':'unavailable','error':'local-profile-unavailable',
                'statisticsExported':False,'networkRequests':0,'modelEvaluated':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--projected',action='store_true');a=p.parse_args()
    if os.geteuid()==0:p.error('Run as the project user; Docker access alone uses sudo.')
    project=a.project.absolute()
    if project.resolve()!=project or not project.is_dir():p.error('Invalid project directory.')
    r=collect(project,projected=a.projected);publish(a.output,r)
    print('Profile state:',r['state']);print('Error category:',r.get('error'))
    d=r.get('diagnostic',{});print('Last phase:',d.get('phase'));print('Elapsed ms:',d.get('elapsedMs'))
    print('No outcome values exported; live statistics cache unchanged. Upload:',a.output)


if __name__=='__main__':
    try:main()
    except (OSError,ValueError):sys.exit('Profile stopped; check paths and permissions. No raw errors exported.')
