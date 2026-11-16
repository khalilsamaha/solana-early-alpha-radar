"""Bind accepted readiness evidence to a target; read-only pre-handoff drift guard.

This is not an approval, rollback config or production command dispatcher.
The caller retains the original report digest and producer pins independently.
"""
from datetime import datetime
from pathlib import Path
import sys
import manifest as m

sys.path.insert(0, str(m.ROOT / 'r1-production-review'))
import intake as i
from readiness_diagnostics import STAGES

MAX_REPORT = 65536
FALSE_FLAGS = ('production_modified', 'provider_connection_opened', 'activation_authorized')


def utc(value):
    m.check(type(value) is str, 'target-time')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    m.check(result.utcoffset() is not None and result.utcoffset().total_seconds() == 0, 'target-time')
    return result


def source_map(value):
    m.check(type(value) is dict and 1 <= len(value) <= 64, 'target-source-map')
    for name, sha in value.items():
        m.check(type(name) is str and not name.startswith('/') and '..' not in Path(name).parts and
                type(sha) is str and m.HEX.fullmatch(sha), 'target-source-map')
    return value


def bind(data, expected_sha256, expected_producer_pins):
    """Validate supplied historical evidence, never query the host or write files."""
    m.check(type(data) is bytes and len(data) <= MAX_REPORT, 'target-report-size')
    m.check(type(expected_sha256) is str and m.HEX.fullmatch(expected_sha256) and
            m.digest(data) == expected_sha256, 'target-report-digest')
    source_map(expected_producer_pins)
    row = m.parse(data)
    m.check(type(row) is dict and type(row.get('schema_version')) is int and row['schema_version'] == 2
            and row.get('status') == 'deployment-inputs-observed-rollout-pending'
            and row.get('observation_attempted') is True and 'failure' not in row and 'error' not in row,
            'target-report-unavailable')
    m.check(all(row.get(key) is False for key in (*FALSE_FLAGS, 'automatic_resume_allowed',
                                                'raw_diagnostics_exported')), 'target-report-authority')
    m.check(source_map(row.get('source_sha256')) == expected_producer_pins, 'target-producer-mismatch')
    started, finished = utc(row['started_utc']), utc(row['finished_utc'])
    m.check(started <= finished, 'target-time-order')
    stages = row.get('stages')
    m.check(type(stages) is list and len(stages) == len(STAGES), 'target-stages')
    previous = started
    for name, stage in zip(STAGES, stages):
        m.check(type(stage) is dict and stage.get('stage') == name and stage.get('status') == 'completed',
                'target-stage-incomplete')
        begin, end = utc(stage['started_utc']), utc(stage['finished_utc'])
        m.check(previous <= begin <= end <= finished, 'target-stage-time')
        previous = end
    observation = row['observation']
    m.check(observation['kind'] == 'r1-production-deployment-inputs' and
            observation['source_sha256'] == expected_producer_pins, 'target-observation-binding')
    m.check(all(observation.get(key) is False for key in (*FALSE_FLAGS, 'container_exec_used',
            'credentials_exported', 'full_effective_configuration_verified',
            'global_owner_exclusivity_verified')), 'target-observation-authority')
    m.check(started <= utc(observation['started_utc']) <= utc(observation['finished_utc']) <= finished,
            'target-observation-time')
    context = observation['context']
    m.check(context.get('schema') == 1 and context.get('kind') == 'read-only-production-context' and
            utc(observation['started_utc']) <= utc(context['started_utc']) <= utc(context['finished_utc'])
            <= utc(observation['finished_utc']), 'target-context-time')
    metadata = i.validate(context['metadata'])
    m.check(context['target'] == i.host.TARGET and context['metadata_sha256'] == i.digest(i.raw(metadata))
            and context['same_projection_observed_twice'] is True, 'target-context-binding')
    m.check(context['source_sha256'] == {k: v for k, v in expected_producer_pins.items()
            if k != 'scripts/r1-production-readiness-kali.sh'}, 'target-context-sources')
    m.check(all(context.get(key) is False for key in (*FALSE_FLAGS, 'sole_owner_verified',
            'full_configuration_verified', 'production_ipc_peer_verified')), 'target-context-authority')
    config = observation['configuration']
    m.check(all(config.get(k) == metadata[n] for k, n in
            (('container_id', 'id'), ('image', 'image'), ('started', 'started'))), 'target-config-binding')
    m.check(type(config['configuration_sha256']) is str and m.HEX.fullmatch(config['configuration_sha256']),
            'target-config-hash')
    m.check(config['raw_environment_exported'] is False and config['raw_command_exported'] is False,
            'target-config-export')
    m.check(metadata['running'] is True and metadata['pid'] > 0 and
            config['command_is_node_scanner'] is True and config['working_directory_is_app'] is True and
            config['configured_source_mode'] in ('direct', 'direct-default') and
            config['shared_socket_configured'] is False, 'target-direct-required')
    identity = context['identity_observation']
    m.check(identity['container_cgroup_binding_observed'] is True and
            identity['same_uid_and_namespace_observed'] is True, 'target-process-unbound')
    m.check(all(identity['container'][k] == metadata[k] for k in
            ('id', 'image', 'pid', 'running', 'started', 'user', 'init', 'restart_policy',
             'readonly_rootfs', 'privileged')), 'target-process-binding')
    for process in (identity['init_process'], identity['main_process']):
        m.check(type(process) is dict and set(process) == {'pid', 'start_ticks', 'uid', 'gid', 'user_namespace'}
                and type(process['pid']) is int and 0 < process['pid'] < 2**31 and
                type(process['start_ticks']) is int and process['start_ticks'] >= 0,
                'target-process-identity')
        m.check(all(type(process[k]) is list and len(process[k]) == 4 and
                    all(type(v) is int and 0 <= v < 2**32 for v in process[k]) for k in ('uid', 'gid'))
                and type(process['user_namespace']) is str and
                i.re.fullmatch(r'user:\[\d+\]', process['user_namespace']), 'target-process-credentials')
    m.check(identity['init_process']['pid'] == metadata['pid'], 'target-init-binding')
    members = observation['running_container_ids']
    m.check(type(members) is list and 1 <= len(members) <= 64 and members == sorted(set(members))
            and all(type(v) is str and m.HEX.fullmatch(v) for v in members)
            and metadata['id'] in members, 'target-census')
    data_mounts = [v for v in metadata['mounts'] if v['destination'] == '/app/data']
    m.check(len(data_mounts) == 1 and data_mounts[0]['type'] == 'volume' and data_mounts[0]['rw'] is True,
            'target-data-volume-required')
    volume = config['data_volume_name']
    m.check(type(volume) is str and i.re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', volume),
            'target-data-volume-name')
    directory, files = config['compose_directory'], config['compose_files']
    m.check(i.absolute(directory) and type(files) is list and 1 <= len(files) <= 8 and
            all(i.absolute(v) for v in files) and len(files) == len(set(files)), 'target-compose-location')
    # Copy only the reviewed projection. No environment names/values or diagnostic text.
    binding = {'schema': 1, 'kind': 'r1-observed-target-binding',
               'report_sha256': expected_sha256, 'producer_source_sha256': dict(expected_producer_pins),
               'observed_utc': row['finished_utc'],
               'target': {'metadata': metadata, 'configuration_projection_sha256': config['configuration_sha256'],
                          'init_process': identity['init_process'], 'main_process': identity['main_process'],
                          'compose_directory': directory, 'compose_files': files, 'data_volume_name': volume},
               'running_container_ids': members,
               'unreviewed_other_container_ids': [v for v in members if v != metadata['id']],
               'full_configuration_verified': False, 'rollback_artifact_verified': False,
               'global_owner_exclusivity_verified': False, 'activation_authorized': False,
               'automatic_resume_allowed': False}
    return m.parse(m.raw(binding))  # No shared mutable references to caller inputs.


def compare(baseline_data, baseline_sha256, fresh_data, fresh_sha256, producer_pins, *, fresh_producer_pins=None):
    """Read-only comparison; the caller must obtain genuinely fresh host evidence.

    Reject replayed/overlapping time windows and drift in config, process, Compose,
    volume or the ownership-review census. A match never proves freshness now or
    global exclusivity, and never authorizes a mutation.
    """
    old = bind(baseline_data, baseline_sha256, producer_pins)
    new = bind(fresh_data, fresh_sha256, producer_pins if fresh_producer_pins is None else fresh_producer_pins)
    m.check(fresh_sha256 != baseline_sha256 and utc(m.parse(fresh_data)['started_utc']) > utc(old['observed_utc']),
            'target-fresh-observation-required')
    m.check(new['target'] == old['target'], 'target-drift')
    m.check(new['running_container_ids'] == old['running_container_ids'], 'target-ownership-census-drift')
    return {'schema': 1, 'kind': 'r1-target-comparison', 'baseline_sha256': baseline_sha256,
            'observation_sha256': fresh_sha256, 'observed_utc': new['observed_utc'],
            'same_target_observed': True, 'global_owner_exclusivity_verified': False,
            'activation_authorized': False, 'automatic_resume_allowed': False}
