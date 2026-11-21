"""Bind the retained controller to accepted target and storage preparation.

Library integration only: no production mutation entry point or activation grant.
The host entry point performs the target-binding inspection read-only.
"""
from pathlib import Path
import re
import sys
import production_control as control
c=control.c
sys.path.insert(0,str(control.ROOT/'r1-deployment'))
import manifest as m
import observed_target as observed
import preparation as prep
import storage
from readiness import CONFIG_FIELDS, HOST_FIELDS


def pins():
    names=('r1-production-control/admission.py','r1-production-control/production_control.py',
           'r1-production-control/command_io.py','r1-control/control.py','r1-deployment/observed_target.py')
    return {**prep.pins(),**{name:m.digest((control.ROOT/name).read_bytes()) for name in names}}


def match_snapshot(data, report_data, report_sha256, producer_pins):
    binding=observed.bind(report_data,report_sha256,producer_pins)
    target=control.project(data);row=c.parse(data)
    metadata=binding['target']['metadata']
    c.check(all(target[k]==metadata[k] for k in ('id','image','name','pid','running','started')),
            'admission-engine-target-drift')
    c.check(target['restart']==metadata['restart_policy'],'admission-restart-drift')
    cfg,host=row['config'],row['host']
    for key,field in (('user','User'),('working_dir','WorkingDir')):
        c.check(cfg.get(field)==metadata[key],'admission-container-config-drift')
    for key,field in (('init','Init'),('readonly_rootfs','ReadonlyRootfs'),('privileged','Privileged'),
                      ('memory','Memory'),('memory_swap','MemorySwap'),('nano_cpus','NanoCpus'),
                      ('pids_limit','PidsLimit'),('network_mode','NetworkMode')):
        c.check(type(host.get(field)) is type(metadata[key]) and host.get(field)==metadata[key],
                'admission-container-config-drift')
    mounts=[{'type':v.get('Type'),'source':v.get('Source'),'destination':v.get('Destination'),
             'rw':v.get('RW')} for v in row['mounts']]
    c.check(mounts==metadata['mounts'],'admission-mount-drift')
    labels=cfg.get('Labels') or {}
    c.check(type(labels) is dict,'admission-labels')
    # Exactly reproduce the accepted readiness producer's bounded projection
    # from this SINGLE inspect response, without persisting any raw values.
    projection={'id':row['id'],'image':row['image'],'started':row['started'],
                **{name:cfg.get(field) for name,field in CONFIG_FIELDS.items()},
                **{name:host.get(field) for name,field in HOST_FIELDS.items()},
                'mounts':row['mounts'],
                'compose_directory':labels.get('com.docker.compose.project.working_dir'),
                'compose_files':labels.get('com.docker.compose.project.config_files')}
    c.check(c.digest(c.raw(projection))==binding['target']['configuration_projection_sha256'],
            'admission-configuration-drift')
    return {'schema':1,'kind':'retained-target-admission-binding',
            'baseline_report_sha256':report_sha256,'producer_source_sha256':dict(producer_pins),
            'baseline_observed_utc':binding['observed_utc'],'target':target,
            'readiness_configuration_sha256':binding['target']['configuration_projection_sha256'],
            'raw_configuration_exported':False,'global_owner_exclusivity_verified':False,
            'process_namespace_reobserved':False,'activation_authorized':False,
            'automatic_resume_allowed':False}


class BoundDocker(control.Docker):
    """One read-only inspection binds an exact ID before constructing controls."""
    def __init__(self,cli,report_data,report_sha256,producer_pins,bounded):
        bound=observed.bind(report_data,report_sha256,producer_pins)
        cid=bound['target']['metadata']['id']
        started=c.now()
        data=bounded(list(cli)+['inspect','--type','container','--format',control.FORMAT,cid],seconds=4,cap=262144)
        self.admission=match_snapshot(data,report_data,report_sha256,producer_pins)
        self.admission.update(started_utc=started,finished_utc=c.now())
        super().__init__(cli,self.admission['target'],bounded)

    @property
    def configuration_sha256(self):return self.admission['readiness_configuration_sha256']


class IsolatedBoundDocker(control.Docker):
    """Bind only a newly owned, exact isolated control fixture; no readiness claim.

    This is the native combined check's adapter. Its immutable configuration is
    observed directly and is never presented as production readiness evidence.
    """
    def __init__(self,cli,cid,token,bounded):
        c.check(isinstance(cid,str) and re.fullmatch('[a-f0-9]{64}',cid),'fixture-exact-id')
        started=c.now()
        def isolated():
            row=c.parse(bounded(list(cli)+['inspect','--type','container','--format',c.FORMAT,cid],seconds=4))
            c.isolated(row,token)
            c.check(row['id']==cid and row['running'] and row['pid']>0 and row['restart']=='unless-stopped',
                    'fixture-running-original')
            return row
        first=isolated()
        target=control.project(bounded(list(cli)+['inspect','--type','container','--format',control.FORMAT,cid],seconds=4,cap=262144))
        c.check(isolated()==first and all(target[k]==first[k] for k in
                ('id','image','pid','started','finished','running','exit_code','restart')),'fixture-binding-drift')
        self.admission={'schema':1,'kind':'retained-isolated-fixture-binding','target':target,
            'isolated':first,'started_utc':started,'finished_utc':c.now(),
            'configuration_binding_sha256':target['config_sha256'],
            'production_readiness_observed':False,'activation_authorized':False,
            'automatic_resume_allowed':False,'global_owner_exclusivity_verified':False}
        super().__init__(cli,target,bounded)

    @property
    def configuration_sha256(self):return self.admission['configuration_binding_sha256']


class Prepared:
    """Gate the actual retained controller using the configured stable registry.

    Explicit library calls can control the bound target, so the caller must obtain
    separate production authority. This component does not confer that authority.
    Shared-owner restoration is deliberately NOT part of this direct-only scope.
    """
    def __init__(self,backend,directory,manifest_sha256,paths):
        c.check(type(backend) in (BoundDocker,IsolatedBoundDocker),'admission-bound-backend-required')
        self.backend=backend;self.directory=Path(directory).absolute();self.sha=manifest_sha256
        self.paths=dict(paths);self.claim=None;self.gates=0
        plan=m.inspect(self.directory,self.sha)
        self.registry=Path(plan['config']['registry_path'])

    def preparation(self):
        plan=m.inspect(self.directory,self.sha);config=plan['config']
        c.check(config['registry_path']==str(self.registry) and
                config['scanner_image']==self.backend.target['image'] and
                config['scanner_config_sha256']==self.backend.configuration_sha256 and
                config['rollback_config_sha256']==self.backend.target['config_sha256'],
                'admission-manifest-target')
        result=prep.inspect(self.registry,self.sha)
        c.check(result['outcome']=='preparation-complete-live-blocked' and
                result['observation']['paths']==self.paths,'admission-preparation-incomplete')
        return plan,result

    def gate(self,action):
        c.check(self.claim is not None and
                c.read(self.registry/'retained-admission.json',65536)==c.raw(self.claim) and
                pins()==self.claim['source_sha256'],'admission-claim-changed')
        plan,result=self.preparation()
        c.check(c.digest(c.raw(result))==self.claim['preparation_sha256'],'admission-preparation-changed')
        sample=storage.observe(self.directory,self.sha,self.paths)
        prep_claim=m.parse(c.read(self.registry/prep.CLAIM,65536))
        prep.validate_observation(sample,plan,prep_claim)
        c.check(sample['capacity_sample_sufficient'],'admission-storage-insufficient')
        for role in storage.ROLES:
            c.check(storage.identity(sample['after'][role])==storage.identity(result['observation']['after'][role]),
                    'admission-storage-replaced')
        c.write_new(self.registry/f'retained-gate-{self.gates:02d}.json',c.raw({
            'scope':'retained-direct-preparation','claim_sha256':c.digest(c.raw(self.claim)),
            'action':action,'observation':sample,'activation_authorized':False}))
        self.gates+=1

    def open(self):
        _,result=self.preparation()
        self.claim={'schema':1,'scope':'retained-direct-preparation','registry':str(self.registry),
                    'manifest_directory':str(self.directory),'manifest_sha256':self.sha,
                    'preparation_sha256':c.digest(c.raw(result)),
                    'admission':self.backend.admission,'source_sha256':pins(),
                    'activation_authorized':False,'automatic_resume_allowed':False}
        c.write_new(self.registry/'retained-admission.json',c.raw(self.claim))
        self.gate('before-control')
        return control.Control(self.registry,self.backend.target,c.digest(c.raw(pins())),self)

    def observe(self,cid):return self.backend.observe(cid)

    def before_dispatch(self,action,cid):
        """Optional additional admission hook, after the last target observation."""

    def mutate(self,action,cid):
        state=control.inspect(self.registry)
        journal_claim=c.parse(c.read(self.registry/'claim.json',16384))
        c.check(state['pending_action']==action and cid==self.backend.target['id'] and
                journal_claim['target']==self.backend.target and
                journal_claim['source_sha256']==c.digest(c.raw(pins())), 'admission-intent-required')
        c.check(self.claim is not None and c.read(self.registry/'retained-admission.json',65536)==c.raw(self.claim),
                'admission-claim-changed')
        # Stop must remain available under insufficient free-space samples.
        # Existing intent/confirmation writes are still required, so this does not
        # promise shutdown on an actually full/broken journal filesystem.
        if action!='stop':self.gate(action)
        control.before(self.backend.observe(cid),state['target'])
        self.before_dispatch(action,cid)
        return self.backend.mutate(action,cid)
