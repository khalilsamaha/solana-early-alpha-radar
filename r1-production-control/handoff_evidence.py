"""Portable complete handoff evidence; read-only replay and explicit quarantine.

Only offline guarded sessions are supported. Original host paths are identities,
never paths to open during verification. No remote transfer or resume operation.
"""
import io
import os
from pathlib import Path
import re
import tempfile
import zipfile
import guarded_session as guarded
import session_evidence as capture_evidence
shared=guarded.shared;c=guarded.c;a=guarded.a;v=shared.supervisor
native=v.native_scanner;app=native.application
MAX_MEMBERS=256;MAX_MEMBER=2*1024**2;MAX_TOTAL=16*1024**2;MAX_MANIFEST=131072
KIND='guarded-offline-handoff-evidence-v1'
REGISTRY_NAMES={a.prep.CLAIM,a.prep.RESULT,'retained-admission.json','claim.json','events.jsonl',
    shared.CLAIM,shared.INTENT,shared.RESULT,v.CLAIM,v.RESULT,'supervision-storage.json','worker-credential.json',
    native.ENDPOINT,native.INTENT,native.IDENTITY,native.PEER,'native-scanner-disposal.json',guarded.CLAIM,guarded.RESULT}
TOP={'manifest/manifest.json','capture/evidence.zip','fixture-intent.json','fixture-disposal.json','fault-ready.json','snapshot.json',
     'result.json','before-corruption.sqlite','before-corruption.bin'}
SERVICE_NAMES={guarded.service.CONTRACT,guarded.service.CLAIM,guarded.service.RESULT}


def allowed(name):
    if type(name) is not str or len(name)>192 or any(x in ('','.','..') for x in name.split('/')):return False
    if name in TOP:return True
    if name.startswith('registry/'):
        rest=name.removeprefix('registry/')
        return rest in REGISTRY_NAMES or re.fullmatch(r'retained-gate-[0-9]{2}\.json',rest) is not None
    if name.startswith('service/'):return name.removeprefix('service/') in SERVICE_NAMES
    return name.startswith('application-data/') and re.fullmatch(r'[A-Za-z0-9_./-]+',name) is not None


def bounded(data):
    c.check(type(data) is dict and 1<=len(data)<=MAX_MEMBERS,'handoff-member-count')
    c.check(all(allowed(k) and type(value) is bytes and len(value)<=MAX_MEMBER for k,value in data.items()),'handoff-member')
    c.check(sum(map(len,data.values()))<=MAX_TOTAL,'handoff-size')


def row(data,name):
    value=c.parse(data[name]);c.check(c.raw(value)==data[name],'handoff-json-canonical');return value


def storage(data):
    files={name.removeprefix('application-data/'):raw for name,raw in data.items() if name.startswith('application-data/')}
    c.check('radar.sqlite' in files and len(files)<=32 and sum(map(len,files.values()))<=app.MAX_STORAGE,'handoff-application-files')
    with tempfile.TemporaryDirectory(prefix='r1-handoff-storage-') as tmp:
        root=Path(tmp);directory=root/app.DATA;directory.mkdir(mode=0o700)
        for name,raw in files.items():
            target=directory/name;target.parent.mkdir(mode=0o700,parents=True,exist_ok=True);c.write_new(target,raw)
        proof=app.storage_proof(root)
        for name,raw in files.items():c.check((directory/name).read_bytes()==raw,'handoff-storage-replay-write')
        return proof


def terminal(claim,manifest,capture,credential_raw,endpoint_raw,identity_raw,peer_raw):
    gate='registry/supervision-storage.json'
    identity=c.parse(identity_raw);peer=c.parse(peer_raw)
    native_evidence={'endpoint_sha256':c.digest(endpoint_raw),'identity_sha256':c.digest(identity_raw),
        'peer_sha256':c.digest(peer_raw),'peer':peer,'development':False,
        'kernel_uid_gid_verified':True,'container_parent_verified':True}
    names=('admission.json','research-retired.json','stopped.json','session.jsonl','capture/ticks.db')
    proof={'kind':'manifest-supervised-capture-fixture','mode':claim['mode'],
        'storage_gate_sha256':None,
        'artifact_sha256':{name:c.digest(capture['capture.db' if name=='capture/ticks.db' else name]) for name in names},
        'research_cleanup':'unsubscribed' if claim['mode'].endswith('-normal') else 'upstream-aborted',
        'discovery_continued_after_retirement':claim['mode'].endswith('-normal'),'capture_thread_joined':True,
        'local_upstream_closed':True,'synthetic_upstream_attempts':1,'research_attachments':1,
        'transport':'unix','peer_uid_verified':False,'provider_connection_opened':False,'real_credential_used':False,
        'activation_authorized':False,'native_peer':native_evidence}
    return proof


def assess(data):
    """Retain valid component facts without promoting an incomplete handoff."""
    bounded(data);reasons=[];facts={'control':None,'service':None,'supervision':None,'capture':None,
                                  'native_application_verified':False,'native_disposal_verified':False}
    context={}
    def stage(name,fn):
        try:fn()
        except KeyError:reasons.append('missing-'+name+'-evidence')
        except Exception:reasons.append('invalid-'+name+'-evidence')
    def authority_stage():
        forbidden={'activation_authorized','production_activation_authorized','live_launch_authorized','automatic_resume_allowed',
            'global_owner_exclusivity_verified','production_modified','provider_connection_opened','provider_origin_attested',
            'remote_preservation_verified','retention_verified','provider_acknowledgement_verified','billing_cutoff_verified',
            'production_handoff_verified','production_profile_accepted','hard_realtime_guarantee'}
        def visit(value):
            if type(value) is dict:
                for key,item in value.items():
                    if key in forbidden:c.check(item is False,'handoff-authority')
                    if key in ('schema','schema_version'):c.check(type(item) is int,'handoff-schema-type')
                    visit(item)
            elif type(value) is list:
                for item in value:visit(item)
        for name,raw in data.items():
            # Application storage is opaque, hash-bound data, not a control
            # receipt schema or a source of operational authority.
            if name.startswith('application-data/'):continue
            if name.endswith('.json'):visit(row(data,name))
            elif name.endswith('.jsonl'):
                for line in raw.splitlines():visit(c.parse(line))
    stage('authority',authority_stage)
    def plan_stage():
        plan=row(data,'manifest/manifest.json')
        c.check(c.raw(plan)==c.raw(a.m.build(plan['config'],plan['policy'])),'handoff-manifest')
        context['plan']=plan;context['sha']=c.digest(data['manifest/manifest.json'])
    stage('manifest',plan_stage)
    def control_stage():
        claim=row(data,'registry/claim.json');state=guarded.pc.replay(claim,data['registry/events.jsonl'])
        c.check(claim['source_sha256']==c.digest(c.raw(a.pins())),'handoff-control-source')
        context.update(control_claim=claim,control=state);facts['control']=state
        if not state['original_restored']:reasons.append('original-restoration-not-confirmed')
    stage('control',control_stage)
    def preparation_stage():
        plan=context['plan'];sha=context['sha'];claim=row(data,'registry/'+a.prep.CLAIM)
        result=row(data,'registry/'+a.prep.RESULT);admission=row(data,'registry/retained-admission.json')
        c.check(claim['manifest_sha256']==sha and claim['source_sha256']==a.prep.pins() and
                claim['registry']==plan['config']['registry_path'],'handoff-preparation-claim')
        c.check(result==a.prep.result_row(data['registry/'+a.prep.CLAIM],result['outcome'],result['observation']) and
                result['outcome']=='preparation-complete-live-blocked','handoff-preparation-result')
        uid=1000 if app.enabled(plan) else claim['registry_identity']['uid']
        c.check(type(uid) is int and uid>=0 and claim['registry_identity']['uid']==uid,'handoff-recorded-owner')
        context['uid']=uid
        a.prep.validate_observation(result['observation'],plan,claim,expected_uid=uid)
        c.check(admission['source_sha256']==a.pins() and admission['manifest_sha256']==sha and
                admission['registry']==claim['registry'] and admission['preparation_sha256']==c.digest(c.raw(result)) and
                admission['admission']['target']==context['control_claim']['target'] and
                admission['admission']['kind']=='retained-isolated-fixture-binding','handoff-admission')
        a.c.isolated(admission['admission']['isolated'],admission['admission']['isolated']['label'])
        names=sorted(name for name in data if re.fullmatch(r'registry/retained-gate-[0-9]{2}\.json',name))
        actions=('before-control','disable_restart','before-shared-session','start_original','restore_restart')
        c.check(1<=len(names)<=len(actions) and (not context['control']['original_restored'] or len(names)==len(actions)),
                'handoff-admission-gates-missing')
        for index,name in enumerate(names):
            gate=row(data,name)
            c.check(name==f'registry/retained-gate-{index:02d}.json' and
                    set(gate)=={'scope','claim_sha256','action','observation','activation_authorized'} and
                    gate['scope']=='retained-direct-preparation' and gate['action']==actions[index] and
                    gate['claim_sha256']==c.digest(data['registry/retained-admission.json']) and
                    gate['activation_authorized'] is False,'handoff-admission-gate')
            a.prep.validate_observation(gate['observation'],plan,claim,expected_uid=uid)
            c.check(gate['observation']['capacity_sample_sufficient'] is True and all(
                a.storage.identity(gate['observation']['after'][role])==a.storage.identity(result['observation']['after'][role])
                for role in a.storage.ROLES),'handoff-admission-storage')
        context['preparation']=result
    stage('preparation',preparation_stage)
    def capture_stage():
        raw=data['capture/evidence.zip'];capture,assessment=capture_evidence.verify(raw,c.digest(raw))
        c.check(assessment['classification'] in ('closed-clean-session-evidence','closed-failed-session-evidence'),'handoff-capture')
        context['capture']=capture;facts['capture']=assessment
    stage('capture',capture_stage)
    def supervision_stage():
        plan=context['plan'];claim=row(data,'registry/'+v.CLAIM);result=row(data,'registry/'+v.RESULT)
        c.check(claim['manifest_sha256']==context['sha'] and claim['source_sha256']==v.r.pins() and
                claim['registry']==plan['config']['registry_path'] and claim['profile']==v.r.profile(plan) and
                claim['preparation_sha256']==c.digest(c.raw(context['preparation'])) and
                claim['mode'] in (app.MODE,*v.session.PIPE_MODES) and claim['native_development'] is False,'handoff-supervision-claim')
        v.session.validate_mode(plan,claim['mode'])
        c.check(result['claim_sha256']==c.digest(data['registry/'+v.CLAIM]) and result['workers_started']==1 and
                result['worker_reaped'] is True and type(result['returncode']) is int and
                result['outcome'] in v.FAILURES|{v.SUCCESS},'handoff-supervision-result')
        c.check(all(result[k] is False for k in ('activation_authorized','automatic_resume_allowed',
                'production_modified','provider_connection_opened')),'handoff-supervision-authority')
        credential=row(data,'registry/worker-credential.json')
        c.check(credential=={'schema':1,'kind':'synthetic-credential-consumption',
                'claim_sha256':c.digest(data['registry/'+v.CLAIM]),'status':'consumed-and-closed','real_credential_used':False},
                'handoff-credential')
        a.prep.validate_observation(row(data,'registry/supervision-storage.json'),plan,
                                   row(data,'registry/'+a.prep.CLAIM),expected_uid=context['uid'])
        context.update(supervision_claim=claim,supervision=result)
        scanner=result['scanner']
        if claim['mode']==app.MODE:
            c.check(set(scanner)=={'kind','development','started','reaped','returncode','result','actor','removed',
                    'process_identity','activation_authorized'} and scanner['kind']=='isolated-native-scanner' and
                    type(scanner['started']) is int and scanner['started']==1 and type(scanner['returncode']) is int and
                    scanner==row(data,'registry/native-scanner-disposal.json') and scanner['development'] is False and
                    scanner['activation_authorized'] is False and scanner['reaped'] is True and
                    scanner['removed'] is True and scanner['returncode']==0,'handoff-native-disposal')
            actor=scanner['actor'];proof=storage(data)
            app.validate_actor_evidence(actor,Path(claim['registry']),complete=True,storage=proof)
            app.validate_result(scanner['result']);c.check(actor['result']==scanner['result'],'handoff-application-result')
            identity=row(data,'registry/'+native.IDENTITY);endpoint=row(data,'registry/'+native.ENDPOINT);peer=row(data,'registry/'+native.PEER)
            native.validate_endpoint(endpoint,data['registry/'+v.CLAIM],plan,False,expected_uid=1000,expected_gid=1000)
            native.validate_identity(identity,data['registry/'+v.CLAIM],plan,False)
            native.validate_peer(peer,identity,data['registry/'+native.IDENTITY],data['registry/'+native.ENDPOINT],
                data['registry/'+v.CLAIM],False,expected_uid=1000,expected_gid=1000)
            c.check(native.same_actor_identity(identity['actor'],actor['initial'],claim['mode']) and
                    identity['process_identity']==scanner['process_identity'],
                    'handoff-native-generation')
            disposal=row(data,'fixture-disposal.json');intent=row(data,'fixture-intent.json')
            c.check(disposal['removed'] is True and disposal['client_reaped'] is True and
                    disposal['id']==context['control_claim']['target']['id'] and disposal['token']==intent['token'] and
                    disposal['name']==intent['name'] and disposal['last_observation']['id']==disposal['id'],
                    'handoff-original-disposal')
            c.isolated(disposal['last_observation'],disposal['token'])
            expected=terminal(claim,plan,context['capture'],data['registry/worker-credential.json'],
                data['registry/'+native.ENDPOINT],data['registry/'+native.IDENTITY],data['registry/'+native.PEER])
        else:
            v.scanner_peer.validate(scanner,claim['mode'],complete=result['outcome']==v.SUCCESS)
            # Development pipe evidence stays explicitly distinguishable.
            expected=terminal(claim,plan,context['capture'],b'',b'{}',b'{}',b'{}')
            expected.pop('native_peer');expected['transport']='pipe'
        expected['storage_gate_sha256']=c.digest(data['registry/supervision-storage.json'])
        terminal_expected={'schema':1,'kind':'synthetic-runtime-terminal','manifest_sha256':context['sha'],
            'profile':claim['profile'],'mode':claim['mode'],'guard_blocked':False,'source_sha256':claim['source_sha256'],
            'production_modified':False,'provider_connection_opened':False,'session_evidence':expected,
            'credential_handoff':'sealed-synthetic-fd','credential_descriptor_closed':True,
            'credential_receipt_sha256':c.digest(data['registry/worker-credential.json'])}
        if result['outcome']==v.SUCCESS:
            c.check(result['returncode']==0 and c.raw(result['terminal'])==c.raw(terminal_expected),'handoff-terminal')
        else:
            c.check(result['terminal'] is None,'handoff-failed-terminal');reasons.append('shared-supervision-not-successful')
        facts['supervision']=result['outcome']
        facts['native_application_verified']=claim['mode']==app.MODE
        facts['native_disposal_verified']=claim['mode']==app.MODE
    stage('supervision',supervision_stage)
    def bridge_stage():
        claim=row(data,'registry/'+shared.CLAIM);intent=row(data,'registry/'+shared.INTENT);result=row(data,'registry/'+shared.RESULT)
        c.check(claim['manifest_sha256']==context['sha'] and claim['source_sha256']==shared.pins() and
                claim['admission_sha256']==c.digest(data['registry/retained-admission.json']) and
                claim['mode']==context['supervision_claim']['mode'],'handoff-bridge-claim')
        first=b''.join(data['registry/events.jsonl'].splitlines(keepends=True)[:4])
        state=guarded.pc.replay(context['control_claim'],first)
        c.check(state['local_stop_verified'] and intent['control_claim_sha256']==c.digest(data['registry/claim.json']) and
                intent['control_events_sha256']==c.digest(first) and intent['stopped_target']==state['target'] and
                intent['claim_sha256']==c.digest(data['registry/'+shared.CLAIM]),'handoff-bridge-intent')
        c.check(result['intent_sha256']==c.digest(data['registry/'+shared.INTENT]) and
                result['supervision_claim_sha256']==c.digest(data['registry/'+v.CLAIM]) and
                result['supervision_result_sha256']==c.digest(data['registry/'+v.RESULT]) and
                context['supervision']['outcome']==v.SUCCESS,'handoff-bridge-result')
        c.check(c.timestamp(context['supervision_claim']['created_utc'])>=c.timestamp(intent['created_utc']) and
                c.timestamp(result['finished_utc'])>=c.timestamp(context['supervision']['finished_utc']),'handoff-bridge-time')
        if context['control']['original_restored']:
            event=c.parse(data['registry/events.jsonl'].splitlines()[4])
            c.check(c.timestamp(event['at'])>=c.timestamp(result['finished_utc']),'handoff-restore-order')
    stage('bridge',bridge_stage)
    def service_stage():
        claim=row(data,'registry/'+guarded.CLAIM);contract=row(data,'service/'+guarded.service.CONTRACT)
        contract_sha=claim['service_contract_sha256'];attempt=data['service/'+guarded.service.CLAIM]
        c.check(context['plan']['config']['service_contract_sha256']==contract_sha,'handoff-service-manifest')
        c.check(contract['directory_identity']['uid']==context['uid'] and contract['lock_identity']['uid']==context['uid'],
                'handoff-service-owner')
        result=data.get('service/'+guarded.service.RESULT)
        assessment=guarded.service.assess(contract,contract_sha,attempt,result);facts['service']=assessment
        c.check(contract['target']==guarded.service.target_identity(context['control_claim']['target']) and
                claim['manifest_sha256']==context['sha'] and claim['source_sha256']==shared.pins() and
                claim['service_attempt_sha256']==c.digest(attempt),'handoff-service-binding')
        attempt_row=c.parse(attempt)
        c.check(attempt_row['manifest_sha256']==context['sha'] and
                attempt_row['run_registry']==context['plan']['config']['registry_path'],'handoff-service-run')
        c.check(claim['budget']==guarded.budget.build(context['control_claim']['target'],context['plan'],claim['budget']['phase_seconds']),
                'handoff-budget-plan')
        complete=row(data,'registry/'+guarded.RESULT);guarded.budget.validate_receipt(claim['budget'],complete['timing'])
        c.check(complete['claim_sha256']==c.digest(data['registry/'+guarded.CLAIM]) and
                complete['control_events_sha256']==c.digest(data['registry/events.jsonl']) and
                complete['shared_result_sha256']==c.digest(data['registry/'+shared.RESULT]) and
                complete['activation_authorized'] is False and complete['automatic_resume_allowed'] is False,'handoff-guard-completion')
        c.check(assessment['status']=='completion-recorded-attempt-consumed','handoff-service-unconfirmed')
        service_result=c.parse(result)
        c.check(service_result['control_events_sha256']==complete['control_events_sha256'] and
                service_result['shared_result_sha256']==complete['shared_result_sha256'] and
                c.timestamp(service_result['finished_utc'])>=c.timestamp(complete['finished_utc']),'handoff-service-completion')
    stage('service',service_stage)
    return {'schema':1,'kind':'portable-offline-handoff-assessment',
        'classification':'quarantined-handoff-evidence' if reasons else 'closed-restored-offline-handoff-evidence',
        'reasons':reasons,'components':facts,'global_owner_exclusivity_verified':False,'production_profile_accepted':False,
        'provider_origin_attested':False,'remote_preservation_verified':False,'retention_verified':False,
        'activation_authorized':False,'automatic_resume_allowed':False}


def pack(data):
    c.check('manifest.json' in data and len(data['manifest.json'])<=MAX_MANIFEST,'handoff-envelope-manifest')
    bounded({key:value for key,value in data.items() if key!='manifest.json'})
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED) as archive:
        for name,raw in sorted(data.items()):
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.create_system=3;info.external_attr=0o100600<<16
            archive.writestr(info,raw)
    value=stream.getvalue();c.check(len(value)<=MAX_TOTAL+MAX_MANIFEST+131072,'handoff-envelope-size');return value


def make(data):
    assessment=assess(data)
    manifest={'schema':1,'kind':KIND,'source_sha256':shared.pins(),
              'members':{name:{'sha256':c.digest(raw),'bytes':len(raw)} for name,raw in data.items()},'assessment':assessment}
    raw=pack({**data,'manifest.json':c.raw(manifest)})
    return raw,assessment


def verify(raw,expected_sha256):
    c.check(type(raw) is bytes and len(raw)<=MAX_TOTAL+MAX_MANIFEST+131072 and
            type(expected_sha256) is str and re.fullmatch('[a-f0-9]{64}',expected_sha256) and
            c.digest(raw)==expected_sha256,'handoff-external-digest')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries=archive.infolist()
        c.check(len(entries)<=MAX_MEMBERS+1 and len({x.filename for x in entries})==len(entries),'handoff-envelope-members')
        for entry in entries:
            c.check((entry.filename=='manifest.json' or allowed(entry.filename)) and entry.compress_type==0 and
                    entry.file_size==entry.compress_size and entry.file_size<=(MAX_MANIFEST if entry.filename=='manifest.json' else MAX_MEMBER)
                    and not entry.flag_bits and not entry.extra and not entry.comment and entry.create_system==3 and
                    entry.external_attr>>16==0o100600,'handoff-envelope-format')
        data={entry.filename:archive.read(entry) for entry in entries}
    c.check(pack(data)==raw,'handoff-envelope-canonical')
    declared=row(data,'manifest.json');data.pop('manifest.json');assessment=assess(data)
    expected={'schema':1,'kind':KIND,'source_sha256':shared.pins(),
              'members':{name:{'sha256':c.digest(value),'bytes':len(value)} for name,value in data.items()},'assessment':assessment}
    c.check(c.raw(declared)==c.raw(expected),'handoff-envelope-binding')
    return data,assessment


def snapshot(root,registry,service_directory):
    """Bounded copies of a completed runner's known paths; no original-path replay."""
    root=Path(root);registry=Path(registry);service_directory=Path(service_directory)
    data={};status={'schema':1,'kind':'offline-handoff-snapshot','application_snapshot':'not-available',
                    'activation_authorized':False,'automatic_resume_allowed':False}
    def add(path,name,cap=MAX_MEMBER):
        try:raw=c.read(path,cap)
        except FileNotFoundError:return
        c.check(c.read(path,cap)==raw,'handoff-snapshot-changed');data[name]=raw
    for name in TOP-{'capture/evidence.zip','snapshot.json'}:add(root/name,name)
    add(root/'export/session/evidence.zip','capture/evidence.zip')
    for name in sorted(REGISTRY_NAMES):add(registry/name,'registry/'+name)
    for index in range(100):
        name=f'retained-gate-{index:02d}.json';add(registry/name,'registry/'+name)
    for name in sorted(SERVICE_NAMES):add(service_directory/name,'service/'+name)
    try:
        disposal=row(data,'registry/native-scanner-disposal.json')
        c.check(disposal['removed'] is True and disposal['reaped'] is True,'handoff-application-not-quiescent')
        directory=registry/app.DATA;fd=a.storage.open_directory(directory)
        staged={}
        try:
            for count,path in enumerate(directory.rglob('*'),1):
                c.check(count<=64 and not path.is_symlink(),'handoff-application-path')
                if path.is_dir():continue
                name='application-data/'+str(path.relative_to(directory));c.check(allowed(name),'handoff-application-name')
                raw=c.read(path,app.MAX_DATABASE)
                c.check(c.read(path,app.MAX_DATABASE)==raw,'handoff-application-changed');staged[name]=raw
                c.check(len(staged)<=32 and sum(map(len,staged.values()))<=app.MAX_STORAGE,'handoff-application-bound')
            a.prep.same_directory(directory,fd)
            for name,raw in staged.items():
                c.check(c.read(directory/name.removeprefix('application-data/'),app.MAX_DATABASE)==raw,'handoff-application-changed')
        finally:os.close(fd)
        data.update(staged);status['application_snapshot']='confirmed-owned-disposal-stable-byte-copy'
    except Exception:status['application_snapshot']='unavailable-retain-originals-no-quiescence-claim'
    data['snapshot.json']=c.raw(status);bounded(data);return data


def export(root,registry,service_directory,destination):
    destination=Path(destination);a.m.private_parent(destination.parent)
    data=snapshot(root,registry,service_directory);raw,assessment=make(data)
    c.write_new(destination,raw)
    readback=c.read(destination,MAX_TOTAL+MAX_MANIFEST+131072)
    c.check(readback==raw,'handoff-export-readback')
    verified,restored=verify(readback,c.digest(raw));c.check(verified==data and restored==assessment,'handoff-independent-restore')
    return {'schema':1,'sha256':c.digest(raw),'bytes':len(raw),'assessment':assessment,
            'local_export_and_restore_verified':True,'remote_preservation_verified':False,'retention_verified':False,
            'activation_authorized':False,'automatic_resume_allowed':False}
