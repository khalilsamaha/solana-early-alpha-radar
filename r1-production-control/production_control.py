"""Retain the original container through a direct-only suspension round trip.

No shared-owner startup, production launcher, provider closure or automatic
restoration. Full configuration stays in memory; only its digest is retained.
"""
import copy
import importlib.util
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('r1_exact_control', ROOT/'r1-control/control.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
ACTIONS = ('disable_restart', 'stop', 'start_original', 'restore_restart')
SCOPE = 'retained-container-direct-roundtrip'
FORMAT = ('{"id":{{json .Id}},"image":{{json .Image}},"name":{{json .Name}},'
          '"config":{{json .Config}},"host":{{json .HostConfig}},"mounts":{{json .Mounts}},'
          '"running":{{json .State.Running}},"pid":{{json .State.Pid}},'
          '"started":{{json .State.StartedAt}},"finished":{{json .State.FinishedAt}},'
          '"exit_code":{{json .State.ExitCode}},"paused":{{json .State.Paused}},'
          '"restarting":{{json .State.Restarting}},"dead":{{json .State.Dead}},'
          '"oom":{{json .State.OOMKilled}},"error":{{json .State.Error}}}')
FIELDS = {'id', 'image', 'name', 'config_sha256', 'restart', 'stop_seconds',
          'running', 'pid', 'started', 'finished', 'exit_code'}
MAX_LOG = 65536


def project(data):
    """Drop all raw Config/HostConfig values before journaling or reporting."""
    c.check(type(data) is bytes and len(data) <= 262144, 'projection-bound')
    row = c.parse(data)
    c.check(type(row) is dict and set(row) == {'id', 'image', 'name', 'config', 'host', 'mounts',
            'running', 'pid', 'started', 'finished', 'exit_code', 'paused', 'restarting', 'dead', 'oom', 'error'},
            'projection-fields')
    c.check(all(row[k] is False for k in ('paused', 'restarting', 'dead', 'oom')) and row['error'] == '',
            'engine-state-unavailable')
    cfg, host = row['config'], copy.deepcopy(row['host'])
    c.check(type(cfg) is dict and type(host) is dict and type(row['mounts']) is list, 'configuration-fields')
    policy = host.pop('RestartPolicy', None)
    c.check(type(policy) is dict and set(policy) == {'Name', 'MaximumRetryCount'} and
            type(policy['MaximumRetryCount']) is int and policy['MaximumRetryCount'] == 0 and
            policy['Name'] in ('no', 'unless-stopped'), 'restart-policy')
    # Restrict the profile rather than infer safe defaults from an unknown signal.
    c.check(cfg.get('StopSignal') in (None, '', 'SIGTERM', '15'), 'stop-signal')
    seconds = cfg.get('StopTimeout')
    c.check(type(seconds) is int and 1 <= seconds <= 60, 'stop-timeout-required')
    result = {key: row[key] for key in ('id', 'image', 'name', 'running', 'pid', 'started', 'finished', 'exit_code')}
    result.update(config_sha256=c.digest(c.raw({'config': cfg, 'host': host, 'mounts': row['mounts']})),
                  restart=policy['Name'], stop_seconds=seconds)
    validate(result)
    return result


def validate(row):
    c.check(type(row) is dict and set(row) == FIELDS, 'target-fields')
    c.check(type(row['id']) is str and re.fullmatch('[a-f0-9]{64}', row['id']) and
            type(row['image']) is str and re.fullmatch('sha256:[a-f0-9]{64}', row['image']) and
            type(row['config_sha256']) is str and re.fullmatch('[a-f0-9]{64}', row['config_sha256']), 'target-identity')
    c.check(type(row['name']) is str and re.fullmatch('/[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', row['name']), 'target-name')
    c.check(row['restart'] in ('no', 'unless-stopped') and type(row['stop_seconds']) is int and
            1 <= row['stop_seconds'] <= 60, 'target-policy')
    c.check(type(row['running']) is bool and type(row['pid']) is int and 0 <= row['pid'] < 2**31 and
            row['running'] == (row['pid'] > 0) and type(row['exit_code']) is int, 'target-state')
    for key in ('started', 'finished'):
        c.check(type(row[key]) is str and re.fullmatch(r'[0-9TZ:.+\-]{20,40}', row[key]), 'target-time')
        c.timestamp(row[key])


def before(row, expected):
    validate(row)
    c.check(row == expected, 'target-drift')


def after(action, row, prior):
    validate(row)
    if action in ('disable_restart', 'restore_restart'):
        policy = 'no' if action == 'disable_restart' else 'unless-stopped'
        c.check(row == {**prior, 'restart': policy}, 'restart-unconfirmed')
    elif action == 'stop':
        fixed = {k: v for k, v in prior.items() if k not in ('running', 'pid', 'exit_code', 'finished')}
        c.check(all(row[k] == v for k, v in fixed.items()) and row['running'] is False and
                row['pid'] == 0 and row['exit_code'] == 0 and
                c.timestamp(row['finished']) >= c.timestamp(prior['started']), 'stop-unconfirmed')
    elif action == 'start_original':
        fixed = {k: v for k, v in prior.items() if k not in ('running', 'pid', 'started', 'finished', 'exit_code')}
        c.check(all(row[k] == v for k, v in fixed.items()) and row['running'] is True and row['pid'] > 0 and
                row['exit_code'] == 0 and c.timestamp(row['started']) > c.timestamp(prior['finished']),
                'start-unconfirmed')
    else:
        raise ValueError('action')


def replay(claim, data):
    c.check(type(claim) is dict and set(claim) == {'schema', 'scope', 'registry', 'target', 'source_sha256', 'created_utc'}, 'claim-fields')
    c.check(type(claim['schema']) is int and claim['schema'] == 1 and claim['scope'] == SCOPE, 'claim-scope')
    c.check(type(claim['source_sha256']) is str and re.fullmatch('[a-f0-9]{64}', claim['source_sha256']), 'source-identity')
    validate(claim['target'])
    c.check(claim['target']['running'] is True and claim['target']['restart'] == 'unless-stopped', 'initial-state')
    c.check(type(data) is bytes and len(data) <= MAX_LOG and (not data or data.endswith(b'\n')), 'log-boundary')
    previous = c.digest(c.raw(claim)); last_time = c.timestamp(claim['created_utc'])
    current = claim['target']; index = 0; records = 0; pending = None
    for line in data.splitlines():
        row = c.parse(line); body = {k: v for k, v in row.items() if k != 'hash'}
        c.check(set(row) == {'seq', 'action', 'kind', 'previous', 'at', 'receipt', 'hash'} and
                c.raw(row).rstrip(b'\n') == line, 'record-format')
        c.check(index < len(ACTIONS) and type(row['seq']) is int and row['seq'] == records+1 and
                row['action'] == ACTIONS[index] and row['previous'] == previous and
                row['hash'] == c.digest(c.raw(body)), 'record-chain')
        at = c.timestamp(row['at']); c.check(at >= last_time, 'clock-regressed'); last_time = at
        if pending is None:
            c.check(row['kind'] == 'intent' and row['receipt'] is None, 'intent'); pending = ACTIONS[index]
        else:
            receipt = row['receipt']
            c.check(row['kind'] == 'confirmed' and type(receipt) is dict and set(receipt) ==
                    {'scope', 'before', 'after', 'provider_connection_closed', 'billing_cutoff_verified'}, 'receipt-fields')
            c.check(receipt['scope'] == 'docker-local-state-only' and receipt['provider_connection_closed'] is False and
                    receipt['billing_cutoff_verified'] is False, 'remote-claim')
            before(receipt['before'], current); after(pending, receipt['after'], current)
            current = receipt['after']; pending = None; index += 1
        previous = row['hash']; records += 1
    return {'state': ('prepared', 'restart-disabled', 'locally-stopped', 'original-running', 'restart-restored')[index],
            'pending_action': pending, 'records': records, 'last_hash': previous, 'target': current,
            'local_stop_verified': index == 2, 'original_restored': index == 4,
            'reconciliation_required': index != 4, 'automatic_resume_allowed': False,
            'shared_start_authorized': False, 'production_activation_authorized': False,
            'provider_connection_closed': False, 'billing_cutoff_verified': False}


class Control(c.Control):
    scope = SCOPE
    actions = ACTIONS
    def replay(self, claim, data): return replay(claim, data)
    def before(self, row, expected): return before(row, expected)
    def after(self, action, row, prior): return after(action, row, prior)


def inspect(registry):
    registry = Path(registry).absolute()
    c.check(all(not p.is_symlink() for p in (registry, *registry.parents)), 'registry-link')
    claim_bytes = c.read(registry/'claim.json', 16384); data = c.read(registry/'events.jsonl', MAX_LOG)
    claim = c.parse(claim_bytes); c.check(claim['registry'] == str(registry), 'registry-binding')
    result = replay(claim, data)
    c.check(c.read(registry/'claim.json', 16384) == claim_bytes and
            c.read(registry/'events.jsonl', MAX_LOG) == data, 'read-changed')
    return result


class Docker:
    """Explicit command adapter; construct with a separately reviewed target.

    The native check below only constructs this for owned network-none fixtures.
    This is not a production-admission or shared-owner-restoration interface.
    """
    def __init__(self, cli, target, bounded):
        validate(target)
        self.cli = list(cli); self.target = copy.deepcopy(target); self.bounded = bounded

    def observe(self, cid):
        c.check(cid == self.target['id'], 'adapter-target')
        return project(self.bounded(self.cli + ['inspect', '--type', 'container', '--format', FORMAT, cid],
                                    seconds=4, cap=262144))

    def mutate(self, action, cid):
        c.check(cid == self.target['id'] and action in ACTIONS, 'adapter-action')
        commands = {'disable_restart': ['update', '--restart=no', cid],
                    'stop': ['stop', '--timeout', str(self.target['stop_seconds']), cid],
                    'start_original': ['start', cid],
                    'restore_restart': ['update', '--restart=unless-stopped', cid]}
        seconds = self.target['stop_seconds']+5 if action == 'stop' else 10
        return self.bounded(self.cli + commands[action], seconds=seconds, cap=256).decode('ascii').strip()
