"""One consumed attempt across cooperating coordinators and output directories.

A fixed, externally pinned service directory is required. This does not fence
Docker administrators, unrelated programs, other hosts or provider accounts.
No production provisioning or reset CLI is provided.
"""
import fcntl
import os
from pathlib import Path
import re
import stat
import production_control as pc
import admission
c=pc.c;s=admission.storage;p=admission.prep
CONTRACT='service-contract.json';LOCK='service.lock';CLAIM='service-attempt.json';RESULT='service-result.json'


def pins():
    return {name:c.digest((pc.ROOT/name).read_bytes()) for name in
            ('r1-production-control/service_registry.py','r1-production-control/production_control.py',
             'r1-deployment/storage.py','r1-deployment/preparation.py','r1-deployment/manifest.py')}


def file_identity(fd):
    value=os.fstat(fd)
    c.check(stat.S_ISREG(value.st_mode) and value.st_uid==os.getuid() and
            value.st_nlink==1 and stat.S_IMODE(value.st_mode)==0o600,'service-lock-private')
    return {'device':value.st_dev,'inode':value.st_ino,'uid':value.st_uid,
            'mode':stat.S_IMODE(value.st_mode),'ctime_ns':value.st_ctime_ns}


def process_identity():
    value=Path('/proc/self/stat').read_text()
    fields=value[value.rindex(')')+2:].split()
    return {'pid':os.getpid(),'start_ticks':int(fields[19])}


def target_identity(target):
    pc.validate(target)
    return {key:target[key] for key in ('id','image','name','config_sha256','stop_seconds')}


def provision(directory,target):
    """Create a fresh OFFLINE fixture service registry; never modify an old one."""
    identity=target_identity(target)
    directory=Path(directory).absolute();admission.m.private_parent(directory.parent)
    c.check(not directory.exists(),'service-registry-exists');directory.mkdir(mode=0o700)
    fd=s.open_directory(directory);lock=None
    try:
        lock=os.open(LOCK,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=fd)
        os.fsync(lock)
        contract={'schema':1,'kind':'cooperating-offline-service-registry','directory':str(directory),
            'directory_identity':s.metadata(fd),'lock_identity':file_identity(lock),
            'target':identity,'source_sha256':pins(),
            'global_owner_exclusivity_verified':False,'activation_authorized':False,'automatic_resume_allowed':False}
        p.write_at(fd,CONTRACT,contract)
        return c.digest(c.raw(contract))
    finally:
        if lock is not None:os.close(lock)
        os.close(fd)


def validate_contract(value,expected_sha256):
    fields={'schema','kind','directory','directory_identity','lock_identity','target','source_sha256',
            'global_owner_exclusivity_verified','activation_authorized','automatic_resume_allowed'}
    c.check(type(value) is dict and set(value)==fields and type(value['schema']) is int and value['schema']==1 and
            value['kind']=='cooperating-offline-service-registry' and
            c.digest(c.raw(value))==expected_sha256,'service-contract-binding')
    c.check(value['source_sha256']==pins(),'service-source-changed')
    admission.m.absolute(value['directory'])
    for key in ('directory_identity','lock_identity'):
        identity=value[key]
        fields={'device','inode','uid','mode'}|({'ctime_ns'} if key=='lock_identity' else set())
        c.check(type(identity) is dict and set(identity)==fields and
                all(type(x) is int for x in identity.values()) and identity['device']>=0 and identity['inode']>0 and
                identity['uid']>=0 and identity['mode']==(0o700 if key=='directory_identity' else 0o600),
                'service-contract-identity')
    target=value['target']
    c.check(set(target)=={'id','image','name','config_sha256','stop_seconds'} and
            re.fullmatch('[a-f0-9]{64}',target['id']) and re.fullmatch('sha256:[a-f0-9]{64}',target['image']) and
            re.fullmatch('[a-f0-9]{64}',target['config_sha256']) and
            type(target['name']) is str and re.fullmatch('/[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',target['name']) and
            type(target['stop_seconds']) is int and 1<=target['stop_seconds']<=60,'service-contract-target')
    c.check(all(value[key] is False for key in
            ('global_owner_exclusivity_verified','activation_authorized','automatic_resume_allowed')),'service-contract-authority')


def load(directory,expected_sha256):
    directory=Path(directory).absolute();fd=s.open_directory(directory)
    try:
        raw=p.read_at(fd,CONTRACT);value=c.parse(raw)
        c.check(c.raw(value)==raw,'service-contract-canonical');validate_contract(value,expected_sha256)
        c.check(value['directory']==str(directory) and value['directory_identity']==s.metadata(fd),'service-directory-binding')
        p.same_directory(directory,fd)
        return value,raw
    finally:os.close(fd)


def validate_claim(claim,contract_sha256):
    fields={'schema','kind','contract_sha256','manifest_sha256','run_registry','process','created_utc',
            'activation_authorized','automatic_resume_allowed'}
    c.check(type(claim) is dict and set(claim)==fields and type(claim['schema']) is int and claim['schema']==1 and
            claim['kind']=='consumed-cooperating-service-attempt' and claim['contract_sha256']==contract_sha256 and
            type(claim['manifest_sha256']) is str and re.fullmatch('[a-f0-9]{64}',claim['manifest_sha256']),
            'service-attempt-binding')
    admission.m.absolute(claim['run_registry']);c.timestamp(claim['created_utc'])
    proc=claim['process'];c.check(type(proc) is dict and set(proc)=={'pid','start_ticks'} and
            all(type(x) is int and x>0 for x in proc.values()),'service-attempt-process')
    c.check(claim['activation_authorized'] is False and claim['automatic_resume_allowed'] is False,'service-attempt-authority')


def assess(contract,contract_sha256,claim_raw=None,result_raw=None):
    """Portable historical assessment: never probe processes or acquire a lock."""
    validate_contract(contract,contract_sha256)
    status='no-recorded-attempt';claim=None
    if claim_raw is not None:
        claim=c.parse(claim_raw);validate_claim(claim,contract_sha256)
        c.check(c.raw(claim)==claim_raw,'service-attempt-canonical');status='attempt-consumed-completion-unconfirmed'
    if result_raw is not None:
        c.check(claim is not None,'service-orphan-result');result=c.parse(result_raw)
        c.check(set(result)=={'schema','kind','claim_sha256','control_events_sha256','shared_result_sha256','finished_utc',
                'activation_authorized','automatic_resume_allowed'} and type(result['schema']) is int and result['schema']==1 and
                result['kind']=='cooperating-service-attempt-closed' and result['claim_sha256']==c.digest(claim_raw) and
                c.raw(result)==result_raw,'service-result-binding')
        for key in ('control_events_sha256','shared_result_sha256'):
            c.check(type(result[key]) is str and re.fullmatch('[a-f0-9]{64}',result[key]),'service-result-digest')
        c.check(c.timestamp(result['finished_utc'])>=c.timestamp(claim['created_utc']) and
                result['activation_authorized'] is False and result['automatic_resume_allowed'] is False,'service-result-authority')
        status='completion-recorded-attempt-consumed'
    return {'schema':1,'status':status,'contract_sha256':contract_sha256,
            'claim_sha256':None if claim_raw is None else c.digest(claim_raw),
            'current_lock_state_observed':False,'current_process_state_observed':False,
            'global_owner_exclusivity_verified':False,'activation_authorized':False,'automatic_resume_allowed':False}


def inspect(directory,expected_sha256):
    contract,_=load(directory,expected_sha256);directory=Path(directory);fd=s.open_directory(directory)
    try:
        values=[]
        for name in (CLAIM,RESULT):
            try:values.append(p.read_at(fd,name))
            except FileNotFoundError:values.append(None)
        output=assess(contract,expected_sha256,*values)
        for name,original in zip((CLAIM,RESULT),values):
            try:current=p.read_at(fd,name)
            except FileNotFoundError:current=None
            c.check(current==original,'service-evidence-changed')
        p.same_directory(directory,fd);return output
    finally:os.close(fd)


class Lease:
    def __init__(self,directory,contract_sha256,target,manifest_sha256,run_registry):
        self.directory=Path(directory).absolute();self.sha=contract_sha256
        self.contract,self.raw=load(self.directory,self.sha)
        c.check(self.contract['target']==target_identity(target),'service-target-mismatch')
        self.run_registry=Path(run_registry).absolute();admission.m.absolute(str(self.run_registry))
        c.check(self.directory!=self.run_registry and self.directory not in self.run_registry.parents and
                self.run_registry not in self.directory.parents,'service-run-path-overlap')
        c.check(type(manifest_sha256) is str and re.fullmatch('[a-f0-9]{64}',manifest_sha256),'service-manifest-digest')
        self.manifest_sha256=manifest_sha256;self.fd=None;self.lock=None;self.claim=None;self.attempted=False
        self.owner=None

    def __enter__(self):
        c.check(not self.attempted,'service-lease-reuse');self.attempted=True
        self.fd=s.open_directory(self.directory)
        try:
            self.lock=os.open(LOCK,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=self.fd)
            c.check(file_identity(self.lock)==self.contract['lock_identity'],'service-lock-replaced')
            try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise ValueError('service-coordinator-active') from None
            c.check(load(self.directory,self.sha)[1]==self.raw,'service-contract-changed')
            for name in (CLAIM,RESULT):
                try:os.stat(name,dir_fd=self.fd,follow_symlinks=False)
                except FileNotFoundError:continue
                raise ValueError('service-attempt-consumed')
            self.owner=process_identity()
            self.claim={'schema':1,'kind':'consumed-cooperating-service-attempt','contract_sha256':self.sha,
                'manifest_sha256':self.manifest_sha256,'run_registry':str(self.run_registry),'process':self.owner,
                'created_utc':c.now(),'activation_authorized':False,'automatic_resume_allowed':False}
            validate_claim(self.claim,self.sha);p.write_at(self.fd,CLAIM,self.claim);self.check();return self
        except BaseException:self.__exit__();raise

    def check(self):
        c.check(self.fd is not None and self.lock is not None and self.claim is not None,'service-lease-closed')
        c.check(process_identity()==self.owner,'service-process-changed')
        c.check(s.metadata(self.fd)==self.contract['directory_identity'] and
                file_identity(self.lock)==self.contract['lock_identity'],'service-identity-changed')
        probe=os.open(LOCK,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=self.fd)
        try:c.check(file_identity(probe)==self.contract['lock_identity'],'service-lock-replaced')
        finally:os.close(probe)
        c.check(load(self.directory,self.sha)[1]==self.raw and p.read_at(self.fd,CLAIM)==c.raw(self.claim),'service-claim-changed')
        p.same_directory(self.directory,self.fd)

    def record_completion(self,control_events_sha256,shared_result_sha256):
        self.check()
        result={'schema':1,'kind':'cooperating-service-attempt-closed','claim_sha256':c.digest(c.raw(self.claim)),
                'control_events_sha256':control_events_sha256,'shared_result_sha256':shared_result_sha256,
                'finished_utc':c.now(),'activation_authorized':False,'automatic_resume_allowed':False}
        assess(self.contract,self.sha,c.raw(self.claim),c.raw(result));p.write_at(self.fd,RESULT,result)
        self.check();return result

    def __exit__(self,*_):
        if self.lock is not None:os.close(self.lock);self.lock=None
        if self.fd is not None:os.close(self.fd);self.fd=None
