"""One read-only deployment-input observation. No Docker mutations or provider I/O.

Raw Docker environment values exist only in local memory; reports contain a
configuration fingerprint, variable names and fixed-value comparisons. No raw
command, environment value, credential, daemon diagnostic or .env content escapes.
"""
import argparse
import os
from pathlib import Path
import re
import stat
import tempfile
import zipfile
import intake as i
import readiness_diagnostics as diagnostics

# Docker inspect retries typed-template failures against its raw JSON map with
# missingkey=error. Optional leaf access must use index, not .Config.StopSignal:
# an omitted key then projects null instead of aborting the entire observation.
# Required parent objects and identity fields remain required. This projects the
# same allowlisted fields; it never requests whole Config/HostConfig objects.
CONFIG_FIELDS = {'cmd': 'Cmd', 'entrypoint': 'Entrypoint', 'environment': 'Env',
                 'working_dir': 'WorkingDir', 'stop_signal': 'StopSignal',
                 'stop_timeout': 'StopTimeout'}
HOST_FIELDS = {'ports': 'PortBindings', 'tmpfs': 'Tmpfs', 'caps_drop': 'CapDrop',
               'caps_add': 'CapAdd', 'security': 'SecurityOpt'}
FORMAT = ('{"id":{{json .Id}},"image":{{json .Image}},"started":{{json .State.StartedAt}},' +
          ','.join('"' + name + '":{{json (index .' + parent + ' "' + field + '")}}'
                   for parent, fields in (('Config', CONFIG_FIELDS), ('HostConfig', HOST_FIELDS))
                   for name, field in fields.items()) +
          ',"mounts":{{json (index . "Mounts")}},' +
          ','.join('"' + name + '":{{with (index .Config "Labels")}}{{json (index . "' + label +
                   '")}}{{else}}null{{end}}' for name, label in (
                       ('compose_directory', 'com.docker.compose.project.working_dir'),
                       ('compose_files', 'com.docker.compose.project.config_files'))) + '}')
FIELDS = {'id', 'image', 'started', 'cmd', 'entrypoint', 'environment', 'working_dir',
          'ports', 'tmpfs', 'caps_drop', 'caps_add', 'security', 'stop_signal', 'stop_timeout',
          'mounts', 'compose_directory', 'compose_files'}


def pins():
    result = i.pins()
    script = i.REPO/'scripts/r1-production-readiness-kali.sh'
    result[str(script.relative_to(i.REPO))] = i.digest(script.read_bytes())
    return result


def configuration(config):
    data = diagnostics.command(config, 'inspect', '--type', 'container', '--format', FORMAT, i.host.TARGET)
    row = i.host.strict_json(data)
    i.check(type(row) is dict and set(row) == FIELDS, 'readiness-configuration-shape')
    i.check(isinstance(row['id'], str) and re.fullmatch('[a-f0-9]{64}', row['id']) and
            isinstance(row['image'], str) and re.fullmatch('sha256:[a-f0-9]{64}', row['image']) and
            i.safe_text(row['started'], 40), 'readiness-configuration-identity')
    # Omitted optional lists have no entries; malformed non-list values still fail.
    env = [] if row['environment'] is None else row['environment']
    i.check(type(env) is list and len(env) <= 128, 'readiness-environment-bound')
    values = {}
    for item in env:
        i.check(isinstance(item, str) and '=' in item and len(item) <= 8192, 'readiness-environment-shape')
        key, value = item.split('=', 1)
        i.check(re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,127}', key) and key not in values,
                'readiness-environment-name')
        values[key] = value
    mode = values.get('PUMPPORTAL_SOURCE', '')
    mounts = [] if row['mounts'] is None else row['mounts']
    i.check(type(mounts) is list and len(mounts) <= 16 and all(type(m) is dict for m in mounts),
            'readiness-mounts')
    data_mounts = [m for m in mounts if m.get('Destination') == '/app/data']
    volume = data_mounts[0].get('Name') if len(data_mounts) == 1 and data_mounts[0].get('Type') == 'volume' else None
    if not isinstance(volume, str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', volume): volume = None
    compose_files = row['compose_files']
    if not isinstance(compose_files, str) or len(compose_files) > 4096: compose_files = ''
    compose_files = compose_files.split(',')
    if not 1 <= len(compose_files) <= 8 or not all(i.absolute(p) for p in compose_files): compose_files = []
    # Only recognized values are exported; unknowns become a constant marker.
    result = {'container_id': row['id'], 'image': row['image'], 'started': row['started'],
              'configuration_sha256': i.digest(i.raw(row)),
              'environment_variable_names': sorted(values),
              'command_is_node_scanner': row['cmd'] == ['node', 'src/index.js'],
              'entrypoint_is_standard_node': row['entrypoint'] in (None, [], ['docker-entrypoint.sh']),
              'working_directory_is_app': row['working_dir'] == '/app',
              'configured_source_mode': 'direct-default' if mode == '' else mode if mode in ('direct', 'shared') else 'unrecognized',
              'shared_socket_configured': bool(values.get('PUMPPORTAL_SOCKET')),
              'provider_credential_present': bool(values.get('PUMPPORTAL_API_KEY')),
              'data_directory_is_app_data': values.get('DATA_DIR') == '/app/data',
              'data_volume_name': volume,
              'compose_directory': row['compose_directory'] if i.absolute(row['compose_directory']) else None,
              'compose_files': compose_files,
              'stop_timeout_seconds': row['stop_timeout'] if type(row['stop_timeout']) is int and
                                      1 <= row['stop_timeout'] <= 300 else None,
              # Missing/empty signal does not verify the effective stop behavior.
              'standard_term_signal': None if row['stop_signal'] in (None, '') else
                                      row['stop_signal'] in ('SIGTERM', '15'),
              'all_capabilities_dropped': row['caps_drop'] == ['ALL'] and row['caps_add'] in (None, []),
              'no_new_privileges': row['security'] in (['no-new-privileges'], ['no-new-privileges:true']),
              'dashboard_loopback_only': False,
              'tmpfs_tmp_configured': type(row['tmpfs']) is dict and set(row['tmpfs']) == {'/tmp'},
              'raw_environment_exported': False, 'raw_command_exported': False}
    ports = row['ports']
    if type(ports) is dict and set(ports) == {'8787/tcp'} and type(ports['8787/tcp']) is list:
        result['dashboard_loopback_only'] = ports['8787/tcp'] == [{'HostIp': '127.0.0.1', 'HostPort': '8787'}]
    return result


def census(config):
    data = diagnostics.command(config, 'ps', '--no-trunc', '--format', '{{.ID}}')
    values = data.decode('ascii').splitlines()
    i.check(len(values) <= 64 and len(set(values)) == len(values) and
            all(re.fullmatch('[a-f0-9]{64}', value) for value in values), 'readiness-container-census')
    return sorted(values)


def storage(path):
    # Existing filesystem only: never creates or allocates the proposed path.
    try:
        path = Path(path)
        i.check(i.absolute(str(path)) and all(not p.is_symlink() for p in (path, *path.parents)),
                'readiness-storage-path')
        st = path.stat(); i.check(stat.S_ISDIR(st.st_mode), 'readiness-storage-directory')
        fs = os.statvfs(path)
        return {'available': True, 'device': st.st_dev, 'inode': st.st_ino,
                'owner_uid': st.st_uid, 'free_bytes_for_user': fs.f_bavail * fs.f_frsize,
                'free_inodes_for_user': fs.f_favail, 'read_only': bool(fs.f_flag & os.ST_RDONLY),
                'space_reserved': False, 'retention_approved': False}
    except Exception:
        return {'available': False, 'reason': 'filesystem-observation-unavailable',
                'space_reserved': False, 'retention_approved': False}


def dotenv_presence(pid):
    # Metadata only; permission failure is not absence. No container exec.
    try:
        st = Path(f'/proc/{pid}/root/app/.env').lstat()
        return {'observed': True, 'present': True, 'regular_file': stat.S_ISREG(st.st_mode),
                'contents_read': False}
    except FileNotFoundError:
        return {'observed': True, 'present': False, 'contents_read': False}
    except Exception:
        return {'observed': False, 'present': None, 'contents_read': False}


def observe(config, storage_root, *, trace=None, source=None):
    trace = diagnostics.Trace() if trace is None else trace
    before = trace.run('source-before', pins) if source is None else source
    started = i.stamp()
    trace.run('local-docker-path', i.host.trusted_local_docker)
    first = trace.run('configuration-before', configuration, config)
    members = trace.run('census-before', census, config)
    context = trace.run('context-and-process', i.observe, config)
    identity = context['identity_observation']
    dotenv = trace.run('dotenv-metadata', dotenv_presence, identity['main_process']['pid'])
    capacity = trace.run('proposed-storage', storage, storage_root)
    mount_capacity = trace.run('data-mount-storage', lambda: [
        {'destination': m['destination'], 'sample': storage(m['source'])}
        for m in context['metadata']['mounts'] if m['destination'] == '/app/data'])
    second = trace.run('configuration-after', configuration, config)
    after_members = trace.run('census-after', census, config)
    trace.run('configuration-consistency', i.check,
              first == second and members == after_members, 'readiness-configuration-changed')
    trace.run('target-consistency', lambda: i.check(
        first['container_id'] == context['metadata']['id'] and first['image'] == context['metadata']['image'] and
        first['started'] == context['metadata']['started'] and first['container_id'] in members,
        'readiness-target-changed'))
    # Detect restart/PID reuse while filesystem observations were taken.
    trace.run('process-consistency', lambda: i.check(
        i.metadata(config) == context['metadata'] and
        i.host.process_identity(identity['main_process']['pid']) == identity['main_process'],
        'readiness-process-changed'))
    trace.run('source-after', lambda: i.check(pins() == before, 'readiness-source-changed'))
    findings = []
    for field in ('command_is_node_scanner', 'entrypoint_is_standard_node', 'working_directory_is_app',
                  'data_directory_is_app_data', 'all_capabilities_dropped', 'no_new_privileges',
                  'dashboard_loopback_only', 'tmpfs_tmp_configured'):
        if not first[field]: findings.append(field+'-unconfirmed')
    if first['configured_source_mode'] not in ('direct', 'direct-default') or first['shared_socket_configured']:
        findings.append('current-direct-source-unconfirmed')
    if dotenv['present'] is not False: findings.append('image-dotenv-configuration-unreviewed')
    if first['data_volume_name'] is None: findings.append('existing-data-volume-name-unconfirmed')
    if first['compose_directory'] is None or not first['compose_files']:
        findings.append('original-compose-location-unconfirmed')
    if first['standard_term_signal'] is not True: findings.append('stop-signal-unconfirmed')
    if first['stop_timeout_seconds'] is None: findings.append('stop-timeout-unconfirmed')
    if not capacity['available']: findings.append('proposed-storage-filesystem-unavailable')
    if len(members) != 1: findings.append('other-running-containers-require-ownership-review')
    return {'kind': 'r1-production-deployment-inputs', 'started_utc': started, 'finished_utc': i.stamp(),
            'source_sha256': before, 'configuration': first, 'context': context,
            'running_container_ids': members, 'embedded_dotenv': dotenv,
            'proposed_storage_root': str(storage_root), 'proposed_storage': capacity,
            'existing_data_mount_capacity': mount_capacity, 'findings': findings,
            'docker_environment_read_in_memory': True, 'credentials_exported': False,
            'full_effective_configuration_verified': False, 'global_owner_exclusivity_verified': False,
            'production_modified': False, 'container_exec_used': False,
            'provider_connection_opened': False, 'activation_authorized': False}


def collect(config, storage_root):
    trace = diagnostics.Trace()
    report = {'schema_version': 2, 'status': 'deployment-inputs-unavailable',
              'observation_attempted': False, 'source_sha256': {},
              'production_modified': False, 'provider_connection_opened': False,
              'activation_authorized': False, 'automatic_resume_allowed': False,
              'raw_diagnostics_exported': False, 'started_utc': i.stamp()}
    try:
        report['source_sha256'] = trace.run('source-before', pins)
        report['observation_attempted'] = True
        observation = observe(config, storage_root, trace=trace, source=report['source_sha256'])
        report['observation'] = observation
        report['status'] = 'deployment-inputs-observed-rollout-pending'
    except Exception as exc:
        # Preserve the original safe headline, with source-bound diagnostic detail.
        # Never publish partial configuration/identity as a coherent observation.
        report['error'] = 'deployment-inputs-observation-unavailable'
        report['failure'] = trace.failure or {
            'stage': 'report-assembly', 'code': diagnostics.code(exc), 'site': diagnostics.site(exc)}
    report['stages'] = trace.rows
    report['finished_utc'] = i.stamp()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True); parser.add_argument('--storage-root', required=True)
    args = parser.parse_args(); os.umask(0o077)
    out = Path(args.output).absolute()
    i.check(not out.exists() and all(not p.is_symlink() for p in (out, *out.parents)), 'readiness-output-exists')
    out.mkdir(mode=0o700)
    report = {'schema_version': 2, 'status': 'deployment-inputs-unavailable', 'observation_attempted': False,
              'production_modified': False, 'provider_connection_opened': False,
              'activation_authorized': False, 'started_utc': i.stamp()}
    try:
        with tempfile.TemporaryDirectory(prefix='r1-readiness-empty-config-') as temporary:
            report = collect(Path(temporary), Path(args.storage_root))
    except Exception as exc:
        # Never serialize exception text: Docker/proc/config may contain secrets.
        report.pop('observation', None)
        report['status'] = 'deployment-inputs-unavailable'
        report['error'] = 'deployment-inputs-observation-unavailable'
        report['failure'] = {'stage': 'private-client-configuration',
                             'code': diagnostics.code(exc), 'site': diagnostics.site(exc)}
    report['finished_utc'] = i.stamp()
    i.host.write_report(out/'report.json', report)
    with zipfile.ZipFile(out/'production-readiness.zip', 'x', compression=zipfile.ZIP_STORED) as archive:
        archive.write(out/'report.json', 'report.json')
    print(report['status']); print(out/'production-readiness.zip')
    return 0 if 'observation' in report else 1


if __name__ == '__main__': raise SystemExit(main())
