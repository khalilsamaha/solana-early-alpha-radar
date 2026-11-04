"""Fixed offline large-record comparison. Disposable fixture keys, no sockets."""
import base64
import json
import time
from unittest.mock import patch
from preserved_exit_checks import case
import preflight_checks
import canonical_replay


def run():
    real_scope = canonical_replay.scope
    program_fixture = preflight_checks.program_fixture
    program_bytes = 1024 * 1024

    def large_fixture(*args, **kwargs):
        value = program_fixture(*args, **kwargs)
        row = value['evidence']['accounts']['result']['value'][1]
        raw = base64.b64decode(row['data'][0])
        row['data'][0] = base64.b64encode(raw + bytes(program_bytes - len(raw))).decode()
        return value

    rows = []
    with patch.object(preflight_checks, 'program_fixture', large_fixture):
        for enabled in (False, True, True, False):
            with case() as c:
                before = c.path.read_bytes()
                with patch.object(canonical_replay, 'scope', lambda: real_scope(enabled=enabled)):
                    started = time.perf_counter_ns()
                    result = c.observe()
                    elapsed = (time.perf_counter_ns() - started) / 1_000_000
                if (result['state'] != 'preserved-exit-observation-complete' or
                        before != c.path.read_bytes() or len(c.rpc.calls) != 20):
                    raise ValueError('synthetic-benchmark-did-not-complete')
                rows.append(dict(reuseEnabled=enabled, elapsedMs=round(elapsed, 3),
                    collectionTiming=result['collectionTiming'],
                    canonicalDigestReplay=result['canonicalDigestReplay']))
    return dict(format='canonical-digest-benchmark-1', mode='synthetic-offline',
                programBytes=program_bytes, rows=rows, networkRequests=0,
                userWalletAccessed=False, transactionsSent=0,
                limitations=['Fixture setup is excluded; synthetic provider replies have no network latency.',
                             'Timing is descriptive, not a unit-test threshold or execution approval.',
                             'Small records can have traversal overhead; host acceptance remains separate.'])


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
