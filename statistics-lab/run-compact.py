#!/usr/bin/env python3
"""One bounded derived-cache experiment; original database stays read-only."""
import argparse
import base64
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
def collect(project,runner=subprocess.run):
    manifest=json.loads((ROOT/'deployment/engineering-release-1.json').read_text())
    hashes={k:v for k,v in manifest['scannerFiles'].items() if k.startswith('src/') and k.endswith('.js')}
    source=(ROOT/'statistics-lab/compact-store.mjs').read_bytes()
    if len(source)>32768:raise ValueError('candidate-cap')
    command=['sudo','-n','docker','compose','--project-directory',str(project),'exec','-T','radar','node','--input-type=module','-',json.dumps(hashes,separators=(',',':')),base64.b64encode(source).decode('ascii')]
    try:
        r=runner(command,input=(ROOT/'statistics-lab/compact-benchmark.mjs').read_bytes(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=145)
        if len(r.stdout)>65536:raise ValueError('output-cap')
        report=json.loads(r.stdout)
        if not isinstance(report,dict) or report.get('format')!='statistics-compact-benchmark-1':raise ValueError('format')
        return report
    except (OSError,ValueError,subprocess.SubprocessError):
        return {'format':'statistics-compact-benchmark-1','state':'unavailable','error':'local-benchmark-unavailable','statisticsExported':False,'modelEvaluated':False,'networkRequests':0}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if os.geteuid()==0:p.error('Run as project user; only Docker access uses sudo.')
    project=a.project.absolute()
    if project.resolve()!=project or not project.is_dir():p.error('Invalid project directory.')
    report=collect(project)
    with a.output.open('xb') as out:
        os.chmod(a.output,0o600)
        out.write(gzip.compress(json.dumps(report,sort_keys=True).encode(),mtime=0))
    print('Benchmark state:',report['state']);print('Error category:',report.get('error'))
    for row in (report.get('diagnostic') or {}).get('rounds',[]):
        print(row['round'],': validation + summary ms:',round(row['validationAndSummaryMs']),'; full round ms:',round(row['elapsedMs']),'; new payloads:',row['readRows'])
    print('Upload only this public report:',a.output)
    print('Keep the private derived cache on the host; original database and live scanner unchanged.')
if __name__=='__main__':
    try:main()
    except (OSError,ValueError):sys.exit('Benchmark stopped; check paths and permissions. No raw errors exported.')
