"""One read-only Docker workload inventory; no global sole-owner claim."""
import argparse
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import zipfile

import intake as i
import readiness as r
import readiness_diagnostics as d
sys.path.insert(0, str(i.REPO / 'r1-deployment'))
import observed_target as target
import storage

FORMAT = ('{"id":{{json .Id}},"image":{{json .Image}},"name":{{json .Name}},'
          '"image_reference":{{json (index .Config "Image")}},'
          '"running":{{json .State.Running}},"pid":{{json .State.Pid}},'
          '"network_mode":{{json (index .HostConfig "NetworkMode")}},'
          '"project":{{with (index .Config "Labels")}}{{json (index . "com.docker.compose.project")}}{{else}}null{{end}},'
          '"service":{{with (index .Config "Labels")}}{{json (index . "com.docker.compose.service")}}{{else}}null{{end}}}')
FIELDS = {'id', 'image', 'name', 'image_reference', 'running', 'pid', 'network_mode', 'project', 'service'}
CHUNK = 8


def pins():
    result = r.pins()
    for name in ('r1-deployment/manifest.py', 'r1-deployment/observed_target.py',
                 'r1-deployment/test_observed_target.py', 'r1-deployment/storage.py',
                 'r1-deployment/test_storage.py', 'scripts/r1-production-ownership-kali.sh'):
        path = i.REPO / name
        i.check(not path.is_symlink(), 'source-link')
        result[name] = i.digest(path.read_bytes())
    return result


def read_report(path):
    path = Path(path).absolute()
    parent = storage.open_directory(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        st = os.fstat(fd)
        i.check(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == os.getuid()
                and not st.st_mode & 0o077 and st.st_size <= target.MAX_REPORT, 'ownership-baseline-file')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(target.MAX_REPORT + 1)
        i.check(len(raw) <= target.MAX_REPORT, 'ownership-baseline-size')
        return raw
    finally:
        os.close(fd)


def find_baseline(root, expected_sha256):
    """Only prior readiness artifacts, never a recursive host/source scan."""
    i.check(type(expected_sha256) is str and re.fullmatch('[a-f0-9]{64}', expected_sha256),
            'ownership-baseline-digest')
    root = Path(root).absolute()
    i.check(all(not p.is_symlink() for p in (root, *root.parents)), 'ownership-baseline-root')
    candidates = []
    for path in root.glob('radar-r1-readiness-*/results/report.json'):
        candidates.append(path)
        i.check(len(candidates) <= 64, 'ownership-baseline-search-bound')
    for path in sorted(candidates):
        # An inaccessible/unsafe historical candidate is not changed or repaired.
        try:
            data = read_report(path)
        except (OSError, ValueError):
            continue
        if i.digest(data) == expected_sha256:
            return data
    raise ValueError('ownership-accepted-baseline-unavailable')


def inventory(config, ids):
    i.check(type(ids) is list and 1 <= len(ids) <= 64 and ids == sorted(set(ids)) and
            all(type(v) is str and re.fullmatch('[a-f0-9]{64}', v) for v in ids), 'ownership-id-set')
    rows = []
    for offset in range(0, len(ids), CHUNK):
        batch = ids[offset:offset + CHUNK]
        data = i.command(config, 'inspect', '--type', 'container', '--format', FORMAT, *batch)
        parsed = [i.host.strict_json(line) for line in data.splitlines()]
        i.check(len(parsed) == len(batch), 'ownership-response-count')
        for row in parsed:
            i.check(type(row) is dict and set(row) == FIELDS, 'ownership-row-fields')
            i.check(type(row['id']) is str and re.fullmatch('[a-f0-9]{64}', row['id']) and
                    type(row['image']) is str and re.fullmatch('sha256:[a-f0-9]{64}', row['image']),
                    'ownership-row-identity')
            i.check(row['running'] is True and type(row['pid']) is int and 0 < row['pid'] < 2**31,
                    'ownership-row-state')
            i.check(type(row['name']) is str and re.fullmatch('/[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', row['name']),
                    'ownership-row-name')
            for key in ('project', 'service'):
                i.check(row[key] is None or type(row[key]) is str and
                        re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', row[key]), 'ownership-compose-label')
            for key in ('image_reference', 'network_mode'):
                i.check(type(row[key]) is str and re.fullmatch('[A-Za-z0-9_./:@-]{0,256}', row[key]),
                        'ownership-row-text')
        i.check(sorted(v['id'] for v in parsed) == batch, 'ownership-response-binding')
        rows.extend(parsed)
    return sorted(rows, key=lambda v: v['id'])


def collect(config, baseline, baseline_sha256):
    report = {'schema': 1, 'kind': 'r1-docker-workload-inventory',
              'status': 'ownership-inventory-unavailable', 'baseline_report_sha256': baseline_sha256,
              'started_utc': i.stamp(), 'observation_attempted': False,
              'production_modified': False, 'container_exec_used': False, 'environment_read': False,
              'command_values_read': False, 'provider_connection_opened': False,
              'global_owner_exclusivity_verified': False, 'activation_authorized': False,
              'automatic_resume_allowed': False}
    stage = 'baseline-validation'
    try:
        row = i.host.strict_json(baseline)
        bound = target.bind(baseline, baseline_sha256, row['source_sha256'])
        stage = 'source-before'; before = pins(); report['source_sha256'] = before
        stage = 'local-docker-path'; report['observation_attempted'] = True
        i.host.trusted_local_docker()
        stage = 'census-before'; ids = r.census(config)
        i.check(bound['target']['metadata']['id'] in ids, 'ownership-baseline-target-unavailable')
        stage = 'workload-metadata'; rows = inventory(config, ids)
        stage = 'census-after'; i.check(r.census(config) == ids, 'ownership-census-changed')
        stage = 'source-after'; i.check(pins() == before, 'ownership-source-changed')
        report.update(status='ownership-inventory-observed-review-pending', workloads=rows,
                      scanner_container_id=bound['target']['metadata']['id'],
                      census_changed_since_baseline=ids != bound['running_container_ids'],
                      docker_request_count=2 + (len(ids) + CHUNK - 1) // CHUNK,
                      review_required_container_ids=[v for v in ids if v != bound['target']['metadata']['id']],
                      excluded_scope=['host-processes', 'other-daemons', 'other-machines',
                                      'provider-connections-and-account-usage'])
    except Exception as exc:
        # No command output, diagnostic text or partial workload set is retained.
        value = exc.args[0] if len(exc.args) == 1 and type(exc.args[0]) is str else None
        allowed = {'ownership-baseline-target-unavailable', 'ownership-response-count', 'ownership-row-fields',
                   'ownership-row-identity', 'ownership-row-state', 'ownership-row-name', 'ownership-compose-label',
                   'ownership-row-text', 'ownership-response-binding', 'ownership-census-changed', 'ownership-source-changed'}
        report['failure'] = {'stage': stage, 'code': value if value in allowed else d.code(exc)}
    report['finished_utc'] = i.stamp()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-root', required=True)
    parser.add_argument('--baseline-sha256', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(); os.umask(0o077)
    out = Path(args.output).absolute()
    i.check(not out.exists() and all(not p.is_symlink() for p in (out, *out.parents)), 'ownership-output-exists')
    out.mkdir(mode=0o700)
    stage = 'baseline-lookup'
    report = {'schema': 1, 'status': 'ownership-inventory-unavailable', 'started_utc': i.stamp(),
              'observation_attempted': False, 'production_modified': False,
              'provider_connection_opened': False, 'activation_authorized': False,
              'automatic_resume_allowed': False}
    try:
        baseline = find_baseline(args.baseline_root, args.baseline_sha256)
        stage = 'private-client-configuration'
        with tempfile.TemporaryDirectory(prefix='r1-ownership-empty-config-') as config:
            report = collect(Path(config), baseline, args.baseline_sha256)
    except Exception as exc:
        report.pop('workloads', None)
        report['status'] = 'ownership-inventory-unavailable'
        allowed = {'ownership-baseline-digest', 'ownership-baseline-root',
                   'ownership-baseline-search-bound', 'ownership-accepted-baseline-unavailable'}
        value = exc.args[0] if len(exc.args) == 1 and type(exc.args[0]) is str else None
        report['failure'] = {'stage': stage, 'code': value if value in allowed else d.code(exc)}
    report['finished_utc'] = i.stamp()
    i.host.write_report(out / 'report.json', report)
    with zipfile.ZipFile(out / 'production-ownership.zip', 'x', compression=zipfile.ZIP_STORED) as archive:
        archive.write(out / 'report.json', 'report.json')
    print(report['status']); print(out / 'production-ownership.zip')
    return 0 if report['status'] == 'ownership-inventory-observed-review-pending' else 1


if __name__ == '__main__': raise SystemExit(main())
