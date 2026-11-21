"""Durable manifest/storage preparation; no production mutation or launch path."""
from datetime import datetime, timezone
import fcntl
import math
import os
from pathlib import Path
import stat
import manifest as m
import storage as s

CLAIM = 'preparation-claim.json'
RESULT = 'preparation-result.json'
LOCK = 'preparation.lock'
BOUND = 262144


def pins():
    names = ('r1-deployment/preparation.py', 'r1-deployment/test_preparation.py',
             'r1-deployment/PREPARATION.md')
    return {**m.sources(), **s.pins(), **{n:m.digest((m.ROOT/n).read_bytes()) for n in names}}


def read_at(fd, name):
    file = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
    try:
        st = os.fstat(file)
        m.check(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == os.getuid()
                and not st.st_mode & 0o077 and st.st_size <= BOUND, 'preparation-private-file')
        with os.fdopen(file, 'rb', closefd=False) as stream:
            data = stream.read(BOUND+1)
        m.check(len(data) <= BOUND, 'preparation-size')
        return data
    finally:
        os.close(file)


def write_at(fd, name, value):
    data = m.raw(value); m.check(len(data) <= BOUND, 'preparation-size')
    file = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    try:
        m.check(os.write(file, data) == len(data), 'preparation-short-write')
        os.fsync(file)
    finally:
        os.close(file)
    os.fsync(fd)
    return data


def same_directory(path, fd):
    other = s.open_directory(path)
    try:
        m.check(s.metadata(fd) == s.metadata(other), 'preparation-registry-replaced')
    finally:
        os.close(other)


def result_row(claim_bytes, outcome, observation):
    return {'schema':1, 'claim_sha256':m.digest(claim_bytes), 'outcome':outcome,
            'observation':observation, 'activation_authorized':False,
            'automatic_resume_allowed':False}


def prepare(manifest_directory, expected_sha256, paths):
    """Consume the configured existing registry before any storage observation.

    All results remain blocked for production. Exceptions never expose provider,
    filesystem or callback text in retained evidence. Failed writes stay retained.
    """
    manifest_directory = m.absolute(str(manifest_directory))
    manifest = m.inspect(manifest_directory, expected_sha256)
    normalized = s.validate_paths(paths, manifest)
    registry = manifest['config']['registry_path']
    m.check(registry is not None, 'preparation-registry-missing')
    fd = s.open_directory(registry)
    lock = None
    try:
        lock = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        st = os.fstat(lock)
        m.check(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == os.getuid()
                and not st.st_mode & 0o077, 'preparation-lock')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        same_directory(registry, fd)
        # Orphan terminal evidence also consumes this registry; never overwrite it.
        try:
            os.stat(RESULT, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError('preparation-result-already-present')
        claim = {'schema':1, 'kind':'r1-production-preparation-only',
                 'manifest_directory':str(manifest_directory), 'manifest_sha256':expected_sha256,
                 'registry':registry, 'registry_identity':s.metadata(fd), 'source_sha256':pins(),
                 'paths':{k:str(v) for k,v in normalized.items()},
                 'created_utc':datetime.now(timezone.utc).isoformat(),
                 'activation_authorized':False, 'automatic_resume_allowed':False}
        claim_bytes = write_at(fd, CLAIM, claim)
        observation = None
        outcome = 'preparation-failed-reconciliation-required'
        try:
            observation = s.observe(manifest_directory, expected_sha256, claim['paths'])
            validate_observation(observation, manifest, claim)
            m.check(pins() == claim['source_sha256'] and
                    m.inspect(manifest_directory, expected_sha256) == manifest, 'preparation-inputs-changed')
            outcome = ('preparation-complete-live-blocked' if observation['capacity_sample_sufficient']
                       else 'preparation-insufficient-live-blocked')
        except Exception:
            # Even a partially returned observation is not accepted after a failure.
            observation = None
        same_directory(registry, fd)
        current_lock = os.stat(LOCK, dir_fd=fd, follow_symlinks=False)
        m.check((current_lock.st_dev,current_lock.st_ino)==(st.st_dev,st.st_ino), 'preparation-lock-replaced')
        m.check(read_at(fd, CLAIM) == claim_bytes, 'preparation-claim-changed')
        terminal = result_row(claim_bytes, outcome, observation)
        write_at(fd, RESULT, terminal)
        return terminal
    finally:
        if lock is not None:
            os.close(lock)
        os.close(fd)


def inspect(registry, expected_manifest_sha256):
    """Historical recovery only. Never observes storage, writes, resumes or retries."""
    registry = str(m.absolute(str(registry)))
    fd = s.open_directory(registry)
    try:
        claim_bytes = read_at(fd, CLAIM)
        claim = m.parse(claim_bytes)
        keys = {'schema','kind','manifest_directory','manifest_sha256','registry','registry_identity',
                'source_sha256','paths','created_utc','activation_authorized','automatic_resume_allowed'}
        m.check(set(claim)==keys and m.raw(claim)==claim_bytes and type(claim['schema']) is int
                and claim['schema']==1 and claim['kind']=='r1-production-preparation-only', 'preparation-claim-format')
        m.check(claim['registry']==registry and claim['registry_identity']==s.metadata(fd), 'preparation-registry-binding')
        m.check(claim['manifest_sha256']==expected_manifest_sha256 and claim['source_sha256']==pins(), 'preparation-source-binding')
        m.check(claim['activation_authorized'] is False and claim['automatic_resume_allowed'] is False, 'preparation-authority')
        manifest = m.inspect(claim['manifest_directory'], expected_manifest_sha256)
        m.check(manifest['config']['registry_path']==registry, 'preparation-manifest-registry')
        s.validate_paths(claim['paths'], manifest)
        stamp = datetime.fromisoformat(claim['created_utc'])
        m.check(stamp.utcoffset() is not None and stamp.utcoffset().total_seconds()==0, 'preparation-time')
        try:
            terminal_bytes = read_at(fd, RESULT)
        except FileNotFoundError:
            terminal_bytes = None
            row = result_row(claim_bytes, 'preparation-unresolved', None)
        else:
            row = m.parse(terminal_bytes)
            outcomes = {'preparation-failed-reconciliation-required','preparation-complete-live-blocked',
                        'preparation-insufficient-live-blocked'}
            m.check(row.get('outcome') in outcomes and
                    m.raw(row)==terminal_bytes and m.raw(row)==m.raw(result_row(claim_bytes,row['outcome'],row.get('observation'))),
                    'preparation-result-binding')
            observation = row['observation']
            if row['outcome']=='preparation-failed-reconciliation-required':
                m.check(observation is None, 'preparation-failed-observation')
            else:
                validate_observation(observation, manifest, claim)
                m.check(observation['capacity_sample_sufficient']==(row['outcome']=='preparation-complete-live-blocked'),
                        'preparation-outcome')
        same_directory(registry, fd)
        m.check(read_at(fd, CLAIM)==claim_bytes, 'preparation-read-changed')
        try:
            after = read_at(fd, RESULT)
        except FileNotFoundError:
            after = None
        m.check(after==terminal_bytes, 'preparation-read-changed')
        return row
    finally:
        os.close(fd)


def validate_observation(row, manifest, claim, *, expected_uid=None):
    """Replay recorded metadata without treating it as a fresh observation."""
    uid=os.getuid() if expected_uid is None else expected_uid
    m.check(type(uid) is int and uid>=0,'preparation-observation-uid')
    fields={'schema','kind','manifest_sha256','source_sha256','paths','before','after','started_utc',
            'finished_utc','elapsed_seconds','available_bytes','required_bytes','status','capacity_sample_sufficient',
            'remaining_blockers','space_reserved','retention_verified','writes_performed','activation_authorized','automatic_resume_allowed'}
    m.check(isinstance(row,dict) and set(row)==fields and type(row['schema']) is int and row['schema']==1 and row['kind']=='r1-storage-observation'
            and row['manifest_sha256']==claim['manifest_sha256'] and row['source_sha256']==s.pins()
            and row['paths']==claim['paths'] and row['remaining_blockers']==manifest['blockers'], 'preparation-observation-binding')
    for key in ('space_reserved','retention_verified','writes_performed','activation_authorized','automatic_resume_allowed'):
        m.check(row[key] is False, 'preparation-observation-authority')
    times=[datetime.fromisoformat(v) for v in (claim['created_utc'],row['started_utc'],row['finished_utc'])]
    m.check(all(v.utcoffset() is not None and v.utcoffset().total_seconds()==0 for v in times)
            and times[0]<=times[1]<=times[2], 'preparation-observation-time')
    m.check(type(row['elapsed_seconds']) in (int,float) and math.isfinite(row['elapsed_seconds'])
            and row['elapsed_seconds']>=0, 'preparation-observation-clock')
    m.check(set(row['before'])==set(s.ROLES) and set(row['after'])==set(s.ROLES), 'preparation-observation-roles')
    values=[]; identities=[]
    for role in s.ROLES:
        before,after = row['before'][role], row['after'][role]
        m.check(s.identity(before)==s.identity(after), 'preparation-observation-identity')
        identities.append((before['device'],before['inode']))
        for sample in (before,after):
            m.check(set(sample)=={'device','inode','uid','mode','available_bytes'} and
                    all(type(sample[k]) is int for k in sample) and sample['device']>=0 and sample['inode']>0
                    and sample['uid']==uid and 0<=sample['mode']<=0o7777 and not sample['mode']&0o077,
                    'preparation-observation-metadata')
            m.check(type(sample['available_bytes']) is int and sample['available_bytes']>=0, 'preparation-observation-space')
            values.append(sample['available_bytes'])
    m.check(len(set(identities))==6 and len({v[0] for v in identities})==1, 'preparation-observation-filesystem')
    available=min(values); required=manifest['capacity']['required_free_bytes']; sufficient=available>=required
    m.check(type(row['available_bytes']) is int and type(row['required_bytes']) is int and
            row['available_bytes']==available and row['required_bytes']==required and
            row['capacity_sample_sufficient'] is sufficient and row['status']==
            ('storage-observed-activation-blocked' if sufficient else 'storage-insufficient-activation-blocked'),
            'preparation-observation-capacity')
