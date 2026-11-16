"""Build an exact scanner image context; no Docker, credentials or service actions."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
BASE='sha256:786529348e5b7b6563a33d8c358c3d03c97110879d6ad53af0fbae65cd0249f9'

def raw(value): return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
def digest(value): return hashlib.sha256(value).hexdigest()
def git(*args): return subprocess.check_output(['git','-C',str(REPO),*args],timeout=15)
def check(ok,reason):
    if not ok: raise ValueError(reason)

def sources():
    names=git('ls-files','-z').decode().split('\0')
    selected=[n for n in names if n=='scanner/package.json' or n.startswith(('scanner/src/','scanner/public/','scanner/scripts/'))]
    check(selected and 'scanner/src/index.js' in selected,'scanner-source-missing')
    selected+=['r1-image/verify.mjs','r1-image/probe.mjs','r1-image/runtime-probe.mjs']
    return sorted(selected)

def source_bytes(names):
    result={}
    for name in names:
        p=REPO/name
        check(all(not x.is_symlink() for x in [p,*p.parents]),'source-link')
        check(p.is_file() and p.stat().st_size<=2*1024**2,'source-file-bound')
        check(not any(x in name.split('/') for x in ('.env','node_modules','data')),'source-excluded')
        result[name]=p.read_bytes()
    check(sum(map(len,result.values()))<=16*1024**2,'source-total-bound')
    package=json.loads(result['scanner/package.json'])
    check(not package.get('dependencies') and not package.get('optionalDependencies'),'unreviewed-runtime-dependency')
    return result

def stage(destination,*,clean=True):
    destination=Path(destination)
    check(not destination.exists(),'context-reuse')
    if clean: check(not git('status','--porcelain').strip(),'source-not-clean')
    tree=git('rev-parse','HEAD^{tree}').decode().strip()
    revision=git('rev-parse','HEAD').decode().strip()
    data=source_bytes(sources())
    destination.mkdir(mode=0o700)
    app=destination/'app';app.mkdir(mode=0o700)
    files={}
    for name,body in data.items():
        target_name=name.removeprefix('r1-image/') if name.startswith('r1-image/') else name
        p=app/target_name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(body);p.chmod(0o644);files[target_name]=digest(body)
    manifest={'schema':1,'source_revision':revision,'source_tree':tree,'base_image':BASE,
        'files':files,'activation_authorized':False,'runtime_dependencies':'node-builtins-only',
        'scope':'scanner-image-candidate-not-production-approval'}
    (app/'manifest.json').write_bytes(raw(manifest))
    # Remove inherited scanner files; use no downloaded dependency or source overlay.
    dockerfile=f'''FROM {BASE}
USER root
RUN rm -rf /app && mkdir -p /app
COPY --chown=1000:1000 app/ /app/
WORKDIR /app
USER 1000:1000
HEALTHCHECK NONE
ENTRYPOINT ["/usr/bin/env", "-i", "PATH=/usr/local/bin:/usr/bin:/bin", "LANG=C.UTF-8", "node"]
CMD ["/app/verify.mjs"]
'''
    (destination/'Dockerfile').write_text(dockerfile)
    return {'manifest':manifest,'manifest_sha256':digest(raw(manifest)),
        'dockerfile_sha256':digest(dockerfile.encode()),'source_sha256':{n:digest(b) for n,b in data.items()}}

def verify_result(value,expected):
    check(value=={'status':'image-bytes-verified','manifest_sha256':expected['manifest_sha256'],
        'files':len(expected['manifest']['files']),'source_tree':expected['manifest']['source_tree'],
        'activation_authorized':False},'image-content-mismatch')

def verify_probe(value,expected,case):
    check(isinstance(value,dict),'probe-type')
    verify_result(value.get('identity'),expected)
    wanted={'normal':('gap',['pumpportal:create','pumpportal:migration','pumpportal:create'],2),
        'sequence-gap':('gap',[],0),'missing-endpoint':('endpoint-refused',[],0)}[case]
    check(value=={'identity':value['identity'],'outcome':wanted[0],'tokens':wanted[1],
        'creations':wanted[2],'upstream_attempts':0,'fetch_attempts':0},'discovery-result-mismatch')
