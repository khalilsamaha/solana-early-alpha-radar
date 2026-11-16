"""Preserve separated-session bytes, including interrupted runs; no remote I/O.

This format has no synthetic-upstream or fixed-run assumption. Source and
receipt bindings are checked, but provider origin and production handoff are
not inferred. A valid archive may intentionally contain quarantined evidence.
"""
from contextlib import ExitStack
import argparse
import io
import os
from pathlib import Path
import re
import stat
import struct
import tempfile
import zipfile

import common as c
import separated_session as s
import archive as candidate_archive
import preserve
import session_bundle
from capture import Limits, private_directory

CAPS = {'admission.json': 65536, 'research-retired.json': 262144,
        'stopped.json': 262144, 'capture.db': 32 * 1024**2,
        'capture-journal': 32 * 1024**2 + 4096, 'session.jsonl': 8 * 1024**2}
MANIFEST_CAP = 131072
MAX_BYTES = sum(CAPS.values()) + MANIFEST_CAP + 8192
KIND = 'r1-separated-session-evidence-v1'
PATHS = {name: name for name in CAPS}
PATHS.update({'capture.db': 'capture/ticks.db', 'capture-journal': 'capture/ticks.db-journal'})


def check(ok, code):
    if not ok: raise c.CaptureError(code)


def row(data):
    value = c.strict_json(data)
    check(c.raw(value) == data, 'evidence-json-canonical')
    return value


def validate_terminal(data, replayed):
    admission, retired, stopped = (row(data[k]) for k in
        ('admission.json', 'research-retired.json', 'stopped.json'))
    expected = {'schema_version': 1, 'kind': 'r1-separated-session-v1',
                'limits': admission['limits'], 'service_seconds': admission['service_seconds'],
                'source_sha256': c.pins(), 'live_launch_authorized': False,
                'production_handoff_verified': False, 'automatic_resume_allowed': False}
    check(c.raw(admission) == c.raw(expected), 'evidence-admission-binding')
    s.validate_limits(Limits(**admission['limits']))
    check(type(admission['service_seconds']) is int and
          admission['limits']['seconds'] <= admission['service_seconds'] <= 172800, 'evidence-duration')
    records = [c.strict_json(line) for line in data['session.jsonl'].splitlines()]
    check(c.raw(records[0]['payload']['limits']) == c.raw(admission['limits']), 'evidence-limits')
    retired_fields = {'schema_version', 'kind', 'admission_sha256', 'research', 'owner',
                      'discovery_frames', 'research_cannot_rearm', 'discovery_continues', 'live_launch_authorized'}
    stopped_fields = {'schema_version', 'kind', 'admission_sha256', 'research', 'owner',
                      'retirement_sha256', 'discovery_frames', 'capture_thread_joined', 'local_upstream_closed',
                      'peer_uid_verified', 'provider_acknowledgement_verified', 'billing_cutoff_verified',
                      'live_launch_authorized', 'production_handoff_verified'}
    check(set(retired) == retired_fields and set(stopped) == stopped_fields, 'evidence-terminal-fields')
    for receipt in (retired, stopped):
        check(type(receipt['schema_version']) is int and receipt['schema_version'] == 1 and
              receipt['admission_sha256'] == c.digest(data['admission.json']) and
              receipt['live_launch_authorized'] is False, 'evidence-terminal-admission')
    check(retired['kind'] == 'r1-research-retired-v1' and
          retired['research_cannot_rearm'] is True and type(retired['discovery_continues']) is bool and
          stopped['kind'] == 'r1-separated-session-stopped-v1' and
          stopped['retirement_sha256'] == c.digest(data['research-retired.json']) and
          stopped['research'] == retired['research'] and
          stopped['capture_thread_joined'] is True and stopped['local_upstream_closed'] is True and
          type(stopped['peer_uid_verified']) is bool and
          all(stopped[k] is False for k in ('provider_acknowledgement_verified', 'billing_cutoff_verified',
                                           'production_handoff_verified')), 'evidence-terminal-binding')
    # No research command can appear after retirement. Discovery counters and
    # the later shutdown reason may change during the separate service lifetime.
    first, last = retired['owner'], stopped['owner']
    check(set(first) == set(last) and all(first[k] == last[k] for k in
          ('upstream_attempts', 'research_attachments', 'commands', 'cleanup',
           'provider_acknowledgement_verified', 'billing_cutoff_verified')) and
          type(first['closed']) is bool and retired['discovery_continues'] is (not first['closed']) and
          type(first['discovery_events_dispatched']) is int and
          type(retired['discovery_frames']) is int and
          0 <= retired['discovery_frames'] <= first['discovery_events_dispatched'] <= last['discovery_events_dispatched'] and
          retired['discovery_frames'] <= stopped['discovery_frames'], 'evidence-retirement-binding')
    return candidate_archive.validate_research(stopped, replayed, records)


def assess(data):
    """Replay copies only. Broken/interrupted original bytes remain unmodified."""
    reasons = []
    replayed = None
    semantic = None
    if 'capture-journal' in data:
        reasons.append('sqlite-rollback-evidence-present')
    elif not {'capture.db', 'session.jsonl'} <= set(data):
        reasons.append('capture-or-journal-missing')
    else:
        with tempfile.TemporaryDirectory(prefix='r1-session-evidence-') as temporary:
            root = Path(temporary); capture = root / 'capture'; capture.mkdir(mode=0o700)
            c.exclusive_file(capture/'ticks.db', data['capture.db'])
            c.exclusive_file(capture/'capture.lock', b'')
            c.exclusive_file(root/'session.jsonl', data['session.jsonl'])
            try:
                replayed = session_bundle.export_session(capture, root/'session.jsonl', root/'replay')
                replayed = {key: replayed[key] for key in ('capture', 'measurement')}
            except Exception:
                reasons.append('capture-journal-replay-unavailable')
    if not {'admission.json', 'research-retired.json', 'stopped.json'} <= set(data):
        reasons.append('terminal-evidence-missing')
    elif replayed is not None:
        try: semantic = validate_terminal(data, replayed)
        except Exception: reasons.append('terminal-evidence-inconsistent')
    outcome = None if semantic is None else semantic['local_session_outcome']
    classification = ('quarantined-incomplete-evidence' if reasons else
                      'closed-clean-session-evidence' if outcome == 'capture-stopped' else
                      'closed-failed-session-evidence')
    return {'classification': classification, 'reasons': reasons, 'local_session_outcome': outcome,
            'replayed': replayed, 'automatic_resume_allowed': False, 'live_launch_authorized': False,
            'provider_origin_attested': False, 'production_handoff_verified': False,
            'remote_preservation_verified': False, 'retention_verified': False}


def manifest(data, assessment):
    return {'schema_version': 1, 'kind': KIND, 'source_sha256': c.pins(),
            'members': {k: {'bytes': len(v), 'sha256': c.digest(v)} for k, v in data.items()},
            'assessment': assessment}


def pack(data):
    check('manifest.json' in data and set(data) <= set(CAPS) | {'manifest.json'}, 'evidence-members')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, value in sorted(data.items()):
            check(type(value) is bytes and len(value) <= CAPS.get(name, MANIFEST_CAP), 'evidence-member-bound')
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3; info.external_attr = 0o100600 << 16
            archive.writestr(info, value)
    return stream.getvalue()


def unpack(raw):
    check(type(raw) is bytes and 22 <= len(raw) <= MAX_BYTES, 'evidence-envelope-bound')
    end = struct.unpack('<4s4H2LH', raw[-22:])
    check(end[0] == b'PK\x05\x06' and end[1:3] == (0, 0) and
          1 <= end[3] == end[4] <= len(CAPS)+1 and not end[7] and
          1 <= end[5] <= 4096 and end[6]+end[5] == len(raw)-22, 'evidence-directory')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist(); names = [e.filename for e in entries]
        check(len(names) == len(set(names)) and 'manifest.json' in names and
              set(names) <= set(CAPS) | {'manifest.json'}, 'evidence-members')
        for entry in entries:
            check(entry.compress_type == 0 and not entry.flag_bits and not entry.extra and not entry.comment and
                  entry.create_system == 3 and entry.external_attr >> 16 == 0o100600 and
                  0 <= entry.file_size <= CAPS.get(entry.filename, MANIFEST_CAP) and
                  entry.compress_size == entry.file_size, 'evidence-member-format')
        data = {entry.filename: archive.read(entry) for entry in entries}
    check(pack(data) == raw, 'evidence-noncanonical-zip')
    return data


def verify(raw, expected_sha256):
    check(isinstance(expected_sha256, str) and re.fullmatch('[a-f0-9]{64}', expected_sha256) and
          c.digest(raw) == expected_sha256, 'evidence-external-checksum')
    before = c.pins(); data = unpack(raw); declared = row(data.pop('manifest.json'))
    assessment = assess(data)
    check(c.raw(declared) == c.raw(manifest(data, assessment)) and c.pins() == before, 'evidence-manifest-binding')
    return data, assessment


def snapshot(control):
    data = {}
    for name, relative in PATHS.items():
        path = c.path_without_links(control/relative)
        try: path.lstat()
        except FileNotFoundError: continue
        data[name] = c.read_private(path, CAPS[name])
    return data


def output_path(output):
    output = c.path_without_links(output); private_directory(output.parent)
    check(not output.exists() and not output.is_symlink(), 'evidence-output-exists')
    # This is a capacity sample on the actual output filesystem, not reservation.
    import shutil
    check(shutil.disk_usage(output.parent).free >= 4*MAX_BYTES + s.SPACE_PREFLIGHT,
          'evidence-insufficient-space')
    return output


def export(control, output):
    control = c.path_without_links(control); private_directory(control)
    output = output_path(output)
    check(control != output and control not in output.parents and output not in control.parents,
          'evidence-output-overlap')
    before = c.pins()
    with ExitStack() as stack:
        # The session owns this lock throughout setup, capture and shutdown.
        stack.enter_context(preserve.existing_lock(control/'capture.lock'))
        capture = control/'capture'
        if capture.exists():
            private_directory(capture)
            stack.enter_context(preserve.existing_lock(capture/'capture.lock'))
        data = snapshot(control); assessment = assess(data)
        raw = pack({**data, 'manifest.json': c.raw(manifest(data, assessment))})
        verify(raw, c.digest(raw))
        check(snapshot(control) == data and c.pins() == before, 'evidence-source-changed')
    output.mkdir(mode=0o700)
    c.exclusive_file(output/'evidence.zip', raw)
    receipt = {'sha256': c.digest(raw), 'bytes': len(raw), 'assessment': assessment}
    c.exclusive_file(output/'report.json', c.raw(receipt))
    return receipt


def restore(path, expected_sha256, output):
    path = c.path_without_links(path); output = output_path(output)
    raw = c.read_private(path, MAX_BYTES); data, assessment = verify(raw, expected_sha256)
    output.mkdir(mode=0o700)
    for name, value in data.items(): c.exclusive_file(output/name, value)
    c.exclusive_file(output/'assessment.json', c.raw(assessment))
    check(c.read_private(path, MAX_BYTES) == raw, 'evidence-input-changed')
    return assessment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    export_parser = sub.add_parser('export'); export_parser.add_argument('--control', required=True)
    restore_parser = sub.add_parser('restore'); restore_parser.add_argument('--archive', required=True)
    restore_parser.add_argument('--sha256', required=True)
    for child in (export_parser, restore_parser): child.add_argument('--output', required=True)
    args = parser.parse_args(); os.umask(0o077)
    try:
        result = (export(Path(args.control), Path(args.output)) if args.mode == 'export' else
                  restore(Path(args.archive), args.sha256, Path(args.output)))
        print(c.canonical(result)); return 0
    except Exception:
        print('session-evidence-unavailable; retain all inputs and partial output'); return 1


if __name__ == '__main__': raise SystemExit(main())
