"""Synthetic host checks; bytes are an ELF envelope fixture, never executable code."""
import base64
import copy
from program import PROGRAM, LOADER, GENESIS, audit, compare, boundaries
from state_fixtures import encoded, received, fake_key, decode, NOW


def fixture(*, authority=True, slot=101):
    pointer = fake_key('programdata')
    program = encoded(b'\x02\0\0\0' + decode(pointer), LOADER, executable=True)
    raw = bytearray(45 + 128)
    raw[:4] = b'\x03\0\0\0'
    raw[4:12] = (90).to_bytes(8, 'little')
    if authority:
        raw[12] = 1
        raw[13:45] = decode(fake_key('upgrade-authority'))
    raw[45:52] = b'\x7fELF\x02\x01\x01'
    return dict(format='swap-program-capture-1', network='devnet', program=PROGRAM,
                origin='synthetic-offline', startedAtMs=NOW, finishedAtMs=NOW+500,
                accountKeys=[PROGRAM, pointer], blockTimeSlot=slot, requests=[], rpcRequestsAttempted=0,
                evidence=dict(genesisBefore=received(GENESIS['devnet']), genesisAfter=received(GENESIS['devnet']),
                    bootstrap=received({'context': {'slot': 100}, 'value': [copy.deepcopy(program)]}),
                    accounts=received({'context': {'slot': slot}, 'value': [program, encoded(raw, LOADER)]}),
                    blockTime=received(NOW//1000)))


def edit(c, offset, value):
    row = c['evidence']['accounts']['result']['value'][1]
    raw = bytearray(base64.b64decode(row['data'][0]))
    raw[offset:offset+len(value)] = value
    row['data'][0] = base64.b64encode(raw).decode()
    return c


def run():
    cases = {'upgradeable-observed': (fixture(), 'deployment-observed'),
             'no-authority-observed': (fixture(authority=False), 'deployment-observed')}
    c = fixture(); c['evidence']['genesisAfter']['result'] = GENESIS['mainnet-beta']
    cases['wrong-cluster'] = (c, 'wrong-cluster')
    c = fixture(); c['evidence']['accounts']['result']['value'][1]['owner'] = PROGRAM
    cases['wrong-loader'] = (c, 'programdata-owner-or-executable')
    c = fixture(); c['evidence']['accounts']['result']['value'][1] = None
    cases['missing-programdata'] = (c, 'programdata-unavailable')
    cases['wrong-tag'] = (edit(fixture(), 0, b'\x01'), 'programdata-tag')
    cases['invalid-option'] = (edit(fixture(), 12, b'\x02'), 'programdata-authority-option')
    cases['future-deployment'] = (edit(fixture(), 4, (102).to_bytes(8, 'little')), 'deployment-slot-after-snapshot')
    cases['non-elf-envelope'] = (edit(fixture(), 45, b'BAD!'), 'program-payload-envelope')
    results = {}
    for name, (c, expected) in cases.items():
        result = audit(c)
        if result.get('reason', result['state']) != expected:
            raise ValueError('Self-check failed: ' + name)
        results[name] = result
    baseline = fixture()
    comparisons = {
        'unchanged': compare(fixture(slot=102), baseline),
        'payload-changed': compare(edit(fixture(slot=102), 110, b'\x01'), baseline),
        'authority-changed': compare(edit(fixture(slot=102), 13, decode(fake_key('replacement'))), baseline),
        'redeployed-same-bytes': compare(edit(fixture(slot=102), 4, (101).to_bytes(8, 'little')), baseline),
        'authority-removed': compare(fixture(authority=False, slot=102), baseline)}
    for name, result in comparisons.items():
        if result['state'] != ('deployment-unchanged' if name == 'unchanged' else 'deployment-changed'):
            raise ValueError('Comparison self-check failed: ' + name)
    return dict(format='swap-program-self-check-1', mode='synthetic-offline',
                casesPassed=len(results)+len(comparisons), cases=results, comparisons=comparisons,
                networkRequests=0, **boundaries())
