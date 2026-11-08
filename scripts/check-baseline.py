#!/usr/bin/env python3
"""Offline B0 regression runner; never installs, deploys or clears a gate."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SUCCESS = 'BASELINE REGRESSION CLEAN'


class StageFailure(RuntimeError):
    pass


def emit(message, log):
    print(message, flush=True)
    log.write(message + '\n')
    log.flush()


def run_stage(label, command, log, *, cwd=ROOT):
    emit('STAGE: ' + label, log)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
               PYTHONWARNINGS='always::ResourceWarning', PYTHONUNBUFFERED='1',
               OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    diagnostics = False
    with subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, errors='replace') as child:
        with child.stdout:
            for line in child.stdout:
                emit(line.rstrip('\n'), log)
                if 'ResourceWarning:' in line or 'Exception ignored' in line:
                    diagnostics = True
        code = child.wait()
    if code or diagnostics:
        raise StageFailure(f'{label}: exit={code}, resource/unraisable diagnostics={diagnostics}')
    emit('STAGE CLEAN: ' + label, log)


def run_all(stages, log):
    for label, command in stages:
        run_stage(label, command, log)
    emit(SUCCESS, log)


def stages(research_python):
    # Check the exact dependency pins without installation or network access.
    check_versions = (
        'from importlib.metadata import version; from pathlib import Path; import sys; '
        'pins=[line.split("==") for line in Path("research-ml/requirements.txt").read_text().splitlines() '
        'if line.strip() and not line.startswith("#")]; '
        'actual={name:version(name) for name,expected in pins}; print(actual); '
        'sys.exit(0 if all(actual[name]==expected for name,expected in pins) else "Research dependency mismatch")'
    )
    commands = [
        ('revision', ['git', 'rev-parse', 'HEAD']),
        ('working tree (must be reviewed with the log)', ['git', 'status', '--short']),
        ('core Python', ['python3', '--version']),
        ('research Python', [research_python, '--version']),
        ('Node', ['node', '--version']),
        ('research dependency pins', [research_python, '-c', check_versions]),
        ('runner rejection checks', [sys.executable, '-m', 'unittest', 'discover',
                                    '-s', 'scripts', '-p', 'test_baseline_runner.py']),
        ('core-base', ['bash', 'scripts/check.sh', 'core-base']),
    ]
    for directory, pattern in [('research-ml', 'test_*.py'),
                               ('forward-study', 'test_model.py'),
                               ('forward-study', 'test_experiment.py'),
                               ('forward-study', 'test_failure_audit.py'),
                               ('availability-study', 'test_*.py')]:
        commands.append((directory + '/' + pattern,
                         [research_python, '-m', 'unittest', 'discover', '-s', directory, '-p', pattern]))
    return commands


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--research-python', required=True, type=Path)
    parser.add_argument('--log', required=True, type=Path)
    args = parser.parse_args(argv)
    if not args.research_python.is_absolute() or not os.access(args.research_python, os.X_OK):
        parser.error('--research-python must be an existing absolute executable path')
    if not args.log.is_absolute():
        parser.error('--log must be an absolute path to a new file')
    os.umask(0o077)
    try:
        with args.log.open('x', encoding='utf-8') as log:
            emit('Offline baseline regression; Kali evidence review is still required.', log)
            try:
                run_all(stages(str(args.research_python)), log)
            except (OSError, StageFailure) as error:
                emit('BASELINE REGRESSION STOPPED: ' + str(error), log)
                return 1
    except OSError as error:
        print('Cannot create new audit log: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
