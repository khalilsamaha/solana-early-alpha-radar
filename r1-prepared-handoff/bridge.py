"""Preparation-bound isolated handoff. Never a production backend selector."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
sys.path.insert(0,str(REPO/'r1-deployment'))
import manifest as m
import storage as s
import preparation as p
sys.path.insert(0,str(REPO/'r1-native-handoff'))
import native as n
h=n.h;c=n.c
STARTS={'bind_endpoint','start_consumer','start_owner','restore_direct'}


def pins():
    names=[*sorted(ROOT.glob('*.py')),ROOT/'README.md',REPO/'scripts/r1-prepared-handoff-kali.sh']
    return {**p.pins(),**n.pins(),**{str(v.relative_to(REPO)):m.digest(v.read_bytes()) for v in names}}


class Guard:
    """A bridge only to the exact accepted network-none native fixture backend."""
    def __init__(self,backend,manifest_directory,manifest_sha256,paths):
        c.check(type(backend) is n.Backend,'isolated-backend-required')
        self.backend=backend;self.directory=Path(manifest_directory);self.sha=manifest_sha256
        self.paths=dict(paths);self.claim=None;self.checks=[]

    def check_preparation(self):
        manifest=m.inspect(self.directory,self.sha)
        c.check(manifest['config']['scanner_image']==c.IMAGE and
            manifest['config']['registry_path']==str(self.backend.registry) and
            manifest['config']['owner_source_sha256']==m.digest((n.ROOT/'broker.py').read_bytes()),'isolated-manifest-binding')
        result=p.inspect(self.backend.registry,self.sha)
        c.check(result['outcome']=='preparation-complete-live-blocked' and result['observation']['paths']==self.paths,
                'preparation-not-complete')
        return result

    def gate(self,action):
        c.check(self.claim is not None,'bridge-unclaimed')
        c.check(c.read(self.backend.registry/'bridge-claim.json',65536)==m.raw(self.claim) and
                pins()==self.claim['source_sha256'],'bridge-claim-changed')
        result=self.check_preparation()
        c.check(m.digest(m.raw(result))==self.claim['preparation_sha256'],'preparation-result-changed')
        observed=s.observe(self.directory,self.sha,self.paths)
        # Reuse the preparation replay validator, including all authority checks.
        prep_claim=m.parse(c.read(self.backend.registry/p.CLAIM,65536))
        p.validate_observation(observed,m.inspect(self.directory,self.sha),prep_claim)
        c.check(observed['capacity_sample_sufficient'],'storage-no-start-headroom')
        for role in s.ROLES:
            c.check(s.identity(observed['after'][role])==s.identity(result['observation']['after'][role]),
                    'storage-generation-changed')
        receipt={'action':action,'bridge_sha256':m.digest(m.raw(self.claim)),'observation':observed,
                 'scope':'isolated-prepared-handoff','activation_authorized':False}
        # Persist the specific pre-dispatch observation. Failure prevents dispatch.
        c.write_new(self.backend.root/f'gate-{len(self.checks):02d}.json',m.raw(receipt))
        self.checks.append(receipt)
        return receipt

    def prepare(self):
        result=self.check_preparation()
        self.claim={'schema':1,'scope':'isolated-prepared-handoff',
            'manifest_sha256':self.sha,'manifest_directory':str(self.directory),
            'registry':str(self.backend.registry),'output':str(self.backend.root),
            'preparation_sha256':m.digest(m.raw(result)),'source_sha256':pins(),
            'development':self.backend.development,'production_activation_authorized':False}
        c.write_new(self.backend.registry/'bridge-claim.json',m.raw(self.claim))
        self.gate('prepare_fixture')
        return self.backend.prepare()

    def perform(self,action,op,known):
        # Admission is checked after coordinator intent, before the native effect.
        state=h.inspect(self.backend.registry)
        claim=m.parse(c.read(self.backend.registry/'handoff-claim.json',65536))
        c.check(state['pending_action']==action and state['known']==known and
                op==h.op_id(claim,state['records']//2),'bridge-intent-required')
        if action in STARTS:
            self.gate(action)
        # Retirement and shutdown retain the accepted exact-actor checks. Disk
        # pressure must not strand the active owner by blocking those operations.
        return self.backend.perform(action,op,known)
