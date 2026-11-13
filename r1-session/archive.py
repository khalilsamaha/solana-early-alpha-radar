"""Portable candidate-session evidence, arbitrary identities, local replay only.

No upload/delete/rotation, mutable retention claim or runnable-service restore.
Incomplete runs remain in place and cannot acquire a complete archive receipt.
"""
from contextlib import ExitStack
import io
from pathlib import Path
import re
import shutil
import stat
import struct
import tempfile
import zipfile

import session as s
from capture import CaptureError, Limits, canonical, digest, exclusive_file, private_directory, strict_json
from handoff import path_without_links, read_private
import session_bundle as b
import sys
sys.path.insert(0, str(s.REPO / 'r1-preservation'))
import preserve
from measurement import command_valid

CAPS = {'admission.json': 65536, 'stopped.json': 262144,
        'session.zip': b.MAX_PACKAGE, 'manifest.json': 65536}
MAX_PACKAGE = sum(CAPS.values()) + 2048
# Conservative available-space preflight for source, package, disposable replay,
# and final isolated restore. This is a sample, NOT a reservation or disk quota.
SPACE_PREFLIGHT = s.SPACE_PREFLIGHT


def row(raw):
    value = strict_json(raw)
    if s.json_bytes(value) != raw:
        raise CaptureError('session-archive-noncanonical-json')
    return value


def pack(contents):
    if set(contents) != set(CAPS):
        raise CaptureError('session-archive-members')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as target:
        for name in sorted(CAPS):
            raw = contents[name]
            if type(raw) is not bytes or not 1 <= len(raw) <= CAPS[name]:
                raise CaptureError('session-archive-member-bound')
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            target.writestr(info, raw)
    return stream.getvalue()


def unpack(raw):
    if type(raw) is not bytes or not 22 <= len(raw) <= MAX_PACKAGE or not raw.startswith(b'PK\x03\x04'):
        raise CaptureError('session-archive-envelope')
    end = struct.unpack('<4s4H2LH', raw[-22:])
    if (end[:5] != (b'PK\x05\x06', 0, 0, 4, 4) or end[7] != 0
            or not 1 <= end[5] <= 1024 or end[6] + end[5] != len(raw) - 22):
        raise CaptureError('session-archive-directory')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) != 4 or {e.filename for e in entries} != set(CAPS) or archive.comment:
            raise CaptureError('session-archive-members')
        for e in entries:
            if (e.compress_type != zipfile.ZIP_STORED or e.flag_bits or e.extra or e.comment
                    or e.create_system != 3 or e.external_attr >> 16 != stat.S_IFREG | 0o600
                    or not 1 <= e.file_size <= CAPS[e.filename] or e.compress_size != e.file_size):
                raise CaptureError('session-archive-format')
        contents = {e.filename: archive.read(e) for e in entries}
    if pack(contents) != raw:
        raise CaptureError('session-archive-noncanonical-zip')
    return contents


def validate(contents, restored):
    admission, stopped = (row(contents[name]) for name in ('admission.json', 'stopped.json'))
    expected = {'schema_version': 1, 'kind': 'r1-session-candidate-v1',
                'limits': admission.get('limits'), 'source_sha256': s.pins(),
                'live_launch_authorized': False, 'production_handoff_verified': False,
                'automatic_resume_allowed': False}
    if canonical(admission) != canonical(expected):
        raise CaptureError('session-archive-admission')
    s.validate_limits(Limits(**admission['limits']))
    inner, _ = b.unpack(contents['session.zip'])
    records = [strict_json(line) for line in inner['session.jsonl'].splitlines()]
    if canonical(records[0]['payload']['limits']) != canonical(admission['limits']):
        raise CaptureError('session-archive-limits')
    expected_keys = {'schema_version', 'kind', 'admission_sha256', 'research', 'owner',
                     'discovery_frames', 'capture_thread_joined', 'local_upstream_closed',
                     'peer_uid_verified', 'provider_acknowledgement_verified', 'billing_cutoff_verified',
                     'live_launch_authorized', 'production_handoff_verified'}
    if (set(stopped) != expected_keys or type(stopped['schema_version']) is not int
            or stopped['schema_version'] != 1 or stopped['kind'] != 'r1-session-stopped-v1'
            or stopped['admission_sha256'] != digest(contents['admission.json'])
            or any(stopped[k] is not True for k in ('capture_thread_joined', 'local_upstream_closed'))
            or type(stopped['peer_uid_verified']) is not bool
            or any(stopped[k] is not False for k in ('provider_acknowledgement_verified', 'billing_cutoff_verified',
                                                   'live_launch_authorized', 'production_handoff_verified'))):
        raise CaptureError('session-archive-stopped-binding')
    research, owner = stopped['research'], stopped['owner']
    measured = restored['measurement']
    if (not isinstance(owner, dict) or not isinstance(research, dict)
            or set(research) != {'outcome', 'research_commands_sent', 'upstream_connections_opened_by_research',
                                'cleanup', 'receive_clock_scope', 'local_send_clock_scope',
                                'provider_acknowledgement_verified', 'billing_cutoff_verified'}
            or set(owner) != {'upstream_attempts', 'research_attachments', 'discovery_events_dispatched',
                      'commands', 'closed', 'reason', 'cleanup', 'provider_acknowledgement_verified', 'billing_cutoff_verified'}
            or type(owner['upstream_attempts']) is not int or owner['upstream_attempts'] != 1
            or type(owner['research_attachments']) is not int or owner['research_attachments'] != 1
            or owner['closed'] is not True or owner['reason'] not in
               ('owner-stop', 'operator-stop', 'discovery-client-ended', 'discovery-output-failed',
                'receive-or-discovery-failed', 'send-uncertain', 'cleanup-failed')
            or owner['provider_acknowledgement_verified'] is not False or owner['billing_cutoff_verified'] is not False
            or research.get('outcome') != measured['session_outcome']
            or type(research['research_commands_sent']) is not int
            or research['research_commands_sent'] != measured['local_sends_completed']
            or type(research['upstream_connections_opened_by_research']) is not int
            or research['upstream_connections_opened_by_research'] != 0
            or research.get('cleanup') != owner['cleanup']
            or research.get('provider_acknowledgement_verified') is not False
            or research.get('billing_cutoff_verified') is not False):
        raise CaptureError('session-archive-research-binding')
    if (research['receive_clock_scope'] != 'capture-thread queue consumption; excludes upstream-to-queue delay'
            or research['local_send_clock_scope'] != 'capture-thread receipt of upstream send completion'):
        raise CaptureError('session-archive-clock-scope')
    cleanup = owner['cleanup']
    if (not isinstance(cleanup, dict) or set(cleanup) != {'outcome', 'reason', 'discovery_continues',
            'provider_unsubscribe_acknowledged', 'billing_cutoff_verified'}
            or cleanup['outcome'] not in ('unsubscribed', 'upstream-aborted')
            or cleanup['reason'] not in ('research-stop', 'deadline', 'worker-unresponsive',
                                        'command-failed', 'research-overflow', 'owner-ended')
            or type(cleanup['discovery_continues']) is not bool
            or cleanup['provider_unsubscribe_acknowledged'] is not False
            or cleanup['billing_cutoff_verified'] is not False
            or restored['capture']['capture_status'] != 'stopped'):
        raise CaptureError('session-archive-cleanup-binding')
    for count in (stopped['discovery_frames'], owner['discovery_events_dispatched']):
        if type(count) is not int or count < 0:
            raise CaptureError('session-archive-discovery-count')
    if stopped['discovery_frames'] > owner['discovery_events_dispatched']:
        raise CaptureError('session-archive-discovery-count')
    commands = owner['commands']
    if not isinstance(commands, list) or not 2 <= len(commands) <= 1024:
        raise CaptureError('session-archive-command-count')
    free = [{'command': {'method': method}, 'state': 'completed', 'cleanup': False}
            for method in ('subscribeNewToken', 'subscribeMigration')]
    if commands[:2] != free:
        raise CaptureError('session-archive-discovery-subscriptions')
    intents = {r['seq']: r['payload']['command'] for r in records if r['kind'] == 'intent'}
    sent = [intents[r['payload']['intent_seq']] for r in records if r['kind'] == 'sent']
    resolved = {r['payload']['intent_seq'] for r in records if r['kind'] in ('sent', 'abandoned')}
    pending = [value for key, value in intents.items() if key not in resolved]
    actual = []
    cleanup_seen = False
    watches = set()
    for command in commands[2:]:
        if (set(command) != {'command', 'state', 'cleanup'} or type(command['cleanup']) is not bool
                or command['state'] not in ('completed', 'uncertain')):
            raise CaptureError('session-archive-command')
        if not command_valid(command['command']) or command['command']['method'] not in ('subscribeTokenTrade', 'unsubscribeTokenTrade'):
            raise CaptureError('session-archive-command')
        if cleanup_seen:
            raise CaptureError('session-archive-command-after-cleanup')
        method, keys = command['command']['method'], command['command']['keys']
        if command['cleanup']:
            cleanup_seen = True
            if method != 'unsubscribeTokenTrade' or keys != sorted(watches):
                raise CaptureError('session-archive-cleanup-command')
        elif command['state'] == 'completed':
            actual.append(command['command'])
        elif command['command'] not in pending:
            raise CaptureError('session-archive-unbound-uncertain-send')
        if method == 'subscribeTokenTrade':
            watches.update(keys)
        else:
            if not set(keys) <= watches:
                raise CaptureError('session-archive-unowned-unsubscribe')
            if command['state'] == 'completed':
                watches.difference_update(keys)
    # A completed upstream send without a durable journal acknowledgement may
    # be the last unresolved intent. It must never become a clean run verdict.
    if actual not in (sent, sent + pending):
        raise CaptureError('session-archive-command-journal-mismatch')
    research_commands = [c for c in commands[2:] if not c['cleanup']]
    expected_commands = [{'command': c, 'state': 'completed', 'cleanup': False} for c in sent]
    allowed = [expected_commands]
    if pending:
        allowed.extend(expected_commands + [{'command': pending[0], 'state': state, 'cleanup': False}]
                       for state in ('completed', 'uncertain'))
    if research_commands not in allowed:
        raise CaptureError('session-archive-research-command-order')
    if measured['session_outcome'] == 'capture-stopped' and (
            cleanup['outcome'] != 'unsubscribed' or cleanup['reason'] != 'research-stop' or watches):
        raise CaptureError('session-archive-clean-stop-contradiction')
    return {'classification': 'complete-session-evidence',
            'local_session_outcome': measured['session_outcome'],
            'local_capture_status': restored['capture']['capture_status'],
            'live_launch_authorized': False, 'remote_preservation_verified': False,
            'retention_verified': False, 'production_handoff_verified': False,
            'provider_origin_attested': False, 'precollection_approval_proven': False,
            'unix_peer_uid_verified': stopped['peer_uid_verified']}


def manifest(contents, assessment):
    return {'schema_version': 1, 'kind': 'r1-candidate-session-archive-v1',
            'members': {k: {'bytes': len(v), 'sha256': digest(v)} for k, v in contents.items()},
            'assessment': assessment, 'source_sha256': s.pins()}


def verify(raw, expected_sha):
    if not isinstance(expected_sha, str) or not re.fullmatch('[0-9a-f]{64}', expected_sha) or digest(raw) != expected_sha:
        raise CaptureError('session-archive-external-checksum')
    before = s.pins()
    contents = unpack(raw)
    declared = row(contents.pop('manifest.json'))
    with tempfile.TemporaryDirectory(prefix='r1-session-review-') as tmp:
        restored = b.restore_bytes(contents['session.zip'], Path(tmp) / 'restored')
        assessment = validate(contents, restored)
    if canonical(declared) != canonical(manifest(contents, assessment)) or s.pins() != before:
        raise CaptureError('session-archive-manifest-binding')
    return contents, assessment


def preflight(output):
    output = path_without_links(output)
    private_directory(output.parent)
    if output.exists() or output.is_symlink():
        raise CaptureError('session-archive-output-exists')
    if shutil.disk_usage(output.parent).free < SPACE_PREFLIGHT:
        raise CaptureError('session-archive-insufficient-space')
    return output


def export(control, output):
    control = path_without_links(control)
    private_directory(control)
    output = preflight(output)
    if output == control or control in output.parents:
        raise CaptureError('session-archive-output-inside-source')
    before = s.pins()
    with ExitStack() as stack:
        stack.enter_context(preserve.existing_lock(control / 'capture.lock'))
        stack.enter_context(preserve.existing_lock(control / 'capture' / 'capture.lock'))
        if set(p.name for p in control.iterdir()) != {'admission.json', 'stopped.json', 'session.jsonl', 'capture', 'capture.lock'}:
            raise CaptureError('session-archive-incomplete-or-extra-evidence')
        if set(p.name for p in (control / 'capture').iterdir()) != {'ticks.db', 'capture.lock'}:
            raise CaptureError('session-archive-rollback-or-extra-evidence')
        paths = {'admission.json': control / 'admission.json', 'stopped.json': control / 'stopped.json',
                 'session.jsonl': control / 'session.jsonl', 'ticks.db': control / 'capture' / 'ticks.db'}
        caps = {**CAPS, 'session.jsonl': 8*1024**2, 'ticks.db': 32*1024**2}
        identities = {k: preserve.identity(p.lstat()) for k, p in paths.items()}
        directories = {p: preserve.identity(p.lstat()) for p in (control, control/'capture')}
        originals = {k: read_private(p, caps[k]) for k, p in paths.items()}
        # Work from isolated copies; no SQLite connection opens on source bytes.
        with tempfile.TemporaryDirectory(prefix='.r1-session-', dir=output.parent) as tmp:
            root = Path(tmp); capture = root / 'capture'; capture.mkdir(mode=0o700)
            exclusive_file(capture / 'ticks.db', originals['ticks.db'])
            exclusive_file(capture / 'capture.lock', b'')
            exclusive_file(root / 'session.jsonl', originals['session.jsonl'])
            exported = b.export_session(capture, root / 'session.jsonl', root / 'export')
            contents = {k: originals[k] for k in ('admission.json', 'stopped.json')}
            contents['session.zip'] = read_private(root / 'export' / 'session.zip', b.MAX_PACKAGE)
            assessment = validate(contents, exported)
            raw = pack({**contents, 'manifest.json': s.json_bytes(manifest(contents, assessment))})
            verify(raw, digest(raw))
        if (any(read_private(p, caps[k]) != originals[k] or preserve.identity(p.lstat()) != identities[k] for k, p in paths.items())
                or any(preserve.identity(p.lstat()) != identity for p, identity in directories.items())):
            raise CaptureError('session-archive-source-changed')
    if s.pins() != before:
        raise CaptureError('session-archive-source-changed')
    output.mkdir(mode=0o700)
    exclusive_file(output / 'archive.zip', raw)
    result = {'schema_version': 1, 'status': 'candidate-session-archived-live-blocked',
              'archive_bytes': len(raw), 'archive_sha256': digest(raw), 'assessment': assessment,
              'source_sqlite_opened': False, 'source_bytes_preserved': True,
              'source_sha256': before, 'automatic_resume_allowed': False}
    exclusive_file(output / 'report.json', s.json_bytes(result))
    return result


def restore(archive, expected_sha, output):
    before = s.pins()
    output = preflight(output)
    raw = read_private(archive, MAX_PACKAGE)
    contents, assessment = verify(raw, expected_sha)
    output.mkdir(mode=0o700)
    for name, value in contents.items():
        exclusive_file(output / name, value)
    b.restore_bytes(contents['session.zip'], output / 'replayed')
    if read_private(archive, MAX_PACKAGE) != raw or s.pins() != before:
        raise CaptureError('session-archive-input-changed')
    result = {'schema_version': 1, 'status': 'candidate-session-restored-live-blocked',
              'archive_sha256': expected_sha, 'archive_bytes': len(raw), 'assessment': assessment,
              'automatic_resume_allowed': False}
    exclusive_file(output / 'report.json', s.json_bytes(result))
    return result
