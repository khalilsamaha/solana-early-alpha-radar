"""Current RPC account relationships for one devnet CPMM contract. Never approves signing."""
import base64
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'swap-contract'))
sys.path.insert(0, str(ROOT / 'recorded-chain'))
from contract import PROGRAM, TOKEN, NATIVE, SYSTEM, DISCRIMINATOR, U64, key, decode, b58, digest, validate, Rejected
from recorded_capture import GENESIS

AUTHORITY = 'CXniRufdq5xL8t8jZAPxsPZDpuudwuJSPWnbcD5Y5Nxq'
LOADER = 'BPFLoaderUpgradeab1e11111111111111111111111'
POOL_FIELDS = ('config', 'creator', 'vault0', 'vault1', 'lpMint', 'mint0', 'mint1', 'program0', 'program1', 'observation')


class StateError(ValueError):
    def __init__(self, reason, state='mismatch'):
        self.reason, self.state = reason, state


def need(ok, reason, state='mismatch'):
    if not ok:
        raise StateError(reason, state)


def integer(value, minimum=0):
    return type(value) is int and minimum <= value <= U64


def u64(raw, offset):
    return int.from_bytes(raw[offset:offset+8], 'little')


def account(row, owner, size, executable=False):
    need(row is not None, 'account-unavailable', 'unavailable')
    need(type(row) is dict, 'account-shape', 'invalid-input')
    need(row.get('owner') == owner and row.get('executable') is executable, 'account-owner-or-executable')
    need(integer(row.get('lamports'), 1), 'account-lamports')
    data = row.get('data')
    need(type(data) is list and len(data) == 2 and data[1] == 'base64' and
         type(data[0]) is str and len(data[0]) <= 6000, 'account-data-encoding', 'unsupported')
    try:
        raw = base64.b64decode(data[0], validate=True)
    except ValueError:
        raise StateError('account-data-encoding', 'invalid-input') from None
    need(base64.b64encode(raw).decode() == data[0], 'account-data-canonical', 'invalid-input')
    need(len(raw) == size, 'account-layout-size', 'unsupported')
    return raw


def anchor(raw, name):
    need(raw[:8] == hashlib.sha256(('account:' + name).encode()).digest()[:8], 'account-discriminator')


def decode_pool(row):
    raw = account(row, PROGRAM, 637); anchor(raw, 'PoolState')
    pool = {name: b58(raw[8+i*32:40+i*32]) for i, name in enumerate(POOL_FIELDS)}
    need(pool['program0'] == TOKEN and pool['program1'] == TOKEN, 'token-program-unsupported', 'unsupported')
    unique = [pool[k] for k in POOL_FIELDS if k not in ('program0', 'program1', 'creator')]
    need(len(set(unique)) == len(unique) and not set(unique) & {SYSTEM,TOKEN,PROGRAM,AUTHORITY}, 'pool-role-alias')
    derived = b58(hashlib.sha256(b'vault_and_lp_mint_auth_seed' + bytes([raw[328]]) +
                                 decode(PROGRAM) + b'ProgramDerivedAddress').digest())
    # Fixed SDK-published PDA anchor; no custom curve arithmetic or generic PDA finder.
    need(raw[328] == 255 and derived == AUTHORITY, 'pool-authority-bump')
    need(raw[329] < 8 and raw[389] <= 2 and raw[390] in (0,1), 'pool-status-or-fee-layout', 'unsupported')
    pool.update(status=raw[329], decimals0=raw[331], decimals1=raw[332],
                openTime=u64(raw,373), creatorFeeOn=raw[389], creatorFeeEnabled=bool(raw[390]),
                accruedFees0=u64(raw,341)+u64(raw,357)+u64(raw,397),
                accruedFees1=u64(raw,349)+u64(raw,365)+u64(raw,405))
    return pool


def option(raw, offset, length=32):
    tag = int.from_bytes(raw[offset:offset+4], 'little')
    need(tag in (0,1), 'invalid-coption', 'unsupported')
    if not tag:
        return None
    data = raw[offset+4:offset+4+length]
    return b58(data) if length == 32 else int.from_bytes(data, 'little')


def mint(row):
    raw = account(row, TOKEN, 82)
    need(raw[45] == 1, 'mint-uninitialized-or-invalid')
    return {'supply': str(u64(raw,36)), 'decimals': raw[44],
            'mintAuthority': option(raw,0), 'freezeAuthority': option(raw,46)}


def token(row, expected_mint, authority):
    raw = account(row, TOKEN, 165)
    need(b58(raw[:32]) == expected_mint and b58(raw[32:64]) == authority, 'token-mint-or-authority')
    need(raw[108] == 1, 'token-uninitialized-frozen-or-invalid')
    amount, reserve = u64(raw,64), option(raw,109,8)
    if expected_mint == NATIVE:
        need(reserve is not None and amount + reserve <= row['lamports'], 'native-vault-backing')
    else:
        need(reserve is None, 'unexpected-native-token')
    return {'amount': str(amount), 'nativeReserve': None if reserve is None else str(reserve),
            'nativeSurplus': None if reserve is None else str(row['lamports']-reserve-amount),
            'delegate': option(raw,72), 'delegatedAmount': str(u64(raw,121)),
            'closeAuthority': option(raw,129)}


def configuration(row):
    raw = account(row, PROGRAM, 236); anchor(raw, 'AmmConfig')
    need(raw[9] in (0,1), 'config-layout', 'unsupported')
    rates = {name: u64(raw, offset) for name, offset in (
        ('trade',12),('protocolShare',20),('fundShare',28),('creator',108),('creatorProtocolShare',116))}
    need(rates['trade'] < 1000000 and rates['creator'] < 1000000 and
         rates['protocolShare'] + rates['fundShare'] <= 1000000 and rates['creatorProtocolShare'] <= 1000000,
         'config-fee-range', 'unsupported')
    return rates


def account_keys(pool_key, pool, packet=None):
    keys = [pool_key,pool['config'],pool['mint0'],pool['mint1'],pool['vault0'],pool['vault1'],pool['observation'],PROGRAM]
    if packet is not None:
        a = packet['policy']['accounts']
        keys += [a['wallet'],a['source'],a['destination']]
    need(len(set(keys)) == len(keys), 'snapshot-role-alias')
    return keys


def received(ev, name):
    item = ev.get(name)
    need(type(item) is dict and item.get('state') == 'received' and 'result' in item,
         'rpc-evidence-unavailable-' + name, 'unavailable')
    return item['result']


def snapshot(value, count):
    need(type(value) is dict and type(value.get('context')) is dict and
         integer(value['context'].get('slot'),1) and type(value.get('value')) is list and
         len(value['value']) == count, 'snapshot-shape', 'invalid-input')
    return value['context']['slot'], value['value']


def discover_pool(rows, tx):
    """One latest RPC transaction supplies an untrusted pool hint, not signed intent evidence."""
    need(type(rows) is list and len(rows) == 1, 'no-latest-program-transaction', 'unavailable')
    row = rows[0]
    need(type(row) is dict and row.get('confirmationStatus') == 'finalized' and 'err' in row and row['err'] is None
         and integer(row.get('slot'),1), 'latest-transaction-not-successful-finalized', 'unavailable')
    need(type(tx) is dict and integer(tx.get('slot'),1) and tx['slot'] == row['slot'] and type(tx.get('meta')) is dict and
         'err' in tx['meta'] and tx['meta']['err'] is None and
         (tx.get('version') == 'legacy' or type(tx.get('version')) is int and tx['version'] == 0), 'discovery-transaction-mismatch')
    transaction = tx.get('transaction')
    need(type(transaction) is dict and type(transaction.get('signatures')) is list and
         bool(transaction['signatures']) and transaction['signatures'][0] == row.get('signature'), 'discovery-signature-mismatch')
    m = transaction.get('message'); need(type(m) is dict, 'discovery-message-shape', 'invalid-input')
    keys = m.get('accountKeys'); need(type(keys) is list and 1 <= len(keys) <= 256, 'discovery-keys', 'invalid-input')
    keys = list(keys)
    loaded = tx['meta'].get('loadedAddresses') or {'writable':[],'readonly':[]}
    need(type(loaded) is dict and all(type(loaded.get(k)) is list for k in ('writable','readonly')), 'discovery-loaded-shape', 'invalid-input')
    keys += loaded['writable'] + loaded['readonly']
    need(len(keys) <= 256 and len(set(key(k) for k in keys)) == len(keys), 'discovery-keys', 'invalid-input')
    outer = m.get('instructions'); inner = tx['meta'].get('innerInstructions') or []
    need(type(outer) is list and len(outer) <= 64 and type(inner) is list and len(inner) <= 64, 'discovery-instruction-cap', 'unsupported')
    instructions = list(outer)
    for group in inner:
        need(type(group) is dict and type(group.get('instructions')) is list, 'discovery-inner-shape', 'invalid-input')
        instructions += group['instructions']
    need(len(instructions) <= 512, 'discovery-instruction-cap', 'unsupported')
    for ix in instructions:
        need(type(ix) is dict and integer(ix.get('programIdIndex')) and ix['programIdIndex'] < len(keys), 'discovery-program-index', 'invalid-input')
        if keys[ix['programIdIndex']] != PROGRAM:
            continue
        data = ix.get('data')
        need(type(data) is str and len(data) <= 100, 'discovery-swap-data', 'unsupported')
        from reconcile import EvidenceError
        try:
            raw = decode(data)
        except EvidenceError:
            raise StateError('discovery-swap-data','invalid-input') from None
        if len(raw) != 24 or raw[:8] != DISCRIMINATOR:
            continue
        indices = ix.get('accounts')
        need(type(indices) is list and len(indices) == 13 and
             all(integer(i) and i < len(keys) for i in indices), 'discovery-swap-accounts', 'unsupported')
        return keys[indices[3]]
    raise StateError('no-supported-swap-in-latest-transaction','unavailable')


def audit(capture):
    result = {'format':'cpmm-state-review-1','state':'unavailable','signingApproved':False,'executionApproved':False,
              'transactionsSent':0,'ledgerUpdated':False,'signatureVerified':False,'deployedBinaryVerified':False,
              'historicalStateProven':False,'independentConsensusVerified':False,'simulationVerified':False,
              'rpcClusterIdentityMatched':False,'poolRelationsMatched':False,'walletAccountsMatched':False,
              'instructionPolicyMatched':False,'priorPolicyProven':False}
    try:
        need(type(capture) is dict and capture.get('format') == 'cpmm-state-capture-1' and
             capture.get('network') == 'devnet', 'capture-format', 'invalid-input')
        need(integer(capture.get('startedAtMs')) and integer(capture.get('finishedAtMs')) and
             0 <= capture['finishedAtMs']-capture['startedAtMs'] <= 45000, 'capture-time-window', 'invalid-input')
        ev = capture.get('evidence'); need(type(ev) is dict, 'capture-evidence', 'invalid-input')
        for k in ('genesisBefore','genesisAfter'):
            need(received(ev,k) == GENESIS['devnet'], 'wrong-cluster')
        result['rpcClusterIdentityMatched'] = True
        pool_key = key(capture.get('pool')); packet = capture.get('packet')
        selection = capture.get('selection')
        need(selection in ('latest-program-transaction','explicit-pool','prior-packet'), 'capture-selection', 'invalid-input')
        if selection == 'latest-program-transaction':
            need(discover_pool(received(ev,'discovery'),received(ev,'transaction')) == pool_key, 'discovered-pool-mismatch')
        need((packet is not None) == (selection == 'prior-packet'), 'packet-selection-mismatch', 'invalid-input')
        if packet is not None:
            contract = validate(packet,now_ms=capture['finishedAtMs'])
            need(contract['state'] == 'instruction-policy-match', 'instruction-policy-not-current', 'unsupported')
            need(packet['policy']['accounts']['pool'] == pool_key, 'policy-pool-mismatch')
            result['instructionPolicyMatched'] = True
        first_slot, first_rows = snapshot(received(ev,'bootstrap'),1)
        first_pool = decode_pool(first_rows[0])
        expected_keys = account_keys(pool_key,first_pool,packet)
        need(capture.get('accountKeys') == expected_keys, 'snapshot-key-binding')
        slot, rows = snapshot(received(ev,'accounts'),len(expected_keys))
        need(slot >= first_slot, 'snapshot-slot-regression')
        if selection == 'latest-program-transaction':
            need(first_slot >= received(ev,'discovery')[0]['slot'], 'discovery-slot-regression')
        pool = decode_pool(rows[0])
        need(account_keys(pool_key,pool,packet) == expected_keys, 'pool-bindings-changed')
        config = configuration(rows[1]); mints = [mint(rows[2]),mint(rows[3])]
        need([m['decimals'] for m in mints] == [pool['decimals0'],pool['decimals1']], 'pool-mint-decimals')
        need(all(pool['mint'+str(i)] != NATIVE or mints[i]['decimals'] == 9 for i in (0,1)), 'native-mint-decimals')
        vaults = [token(rows[4],pool['mint0'],AUTHORITY), token(rows[5],pool['mint1'],AUTHORITY)]
        need(all(pool['mint'+str(i)] == NATIVE or int(vaults[i]['amount']) <= int(mints[i]['supply']) for i in (0,1)),
             'vault-balance-exceeds-mint-supply')
        observation = account(rows[6],PROGRAM,4075); anchor(observation,'ObservationState')
        need(observation[8] in (0,1) and int.from_bytes(observation[9:11],'little') < 100 and
             b58(observation[11:43]) == pool_key, 'observation-pool-binding')
        program = account(rows[7],LOADER,36,True)
        need(int.from_bytes(program[:4],'little') == 2 and program[4:] != bytes(32), 'program-account-layout', 'unsupported')
        block_time = received(ev,'blockTime'); need(integer(block_time), 'block-time-unavailable', 'unavailable')
        need(capture.get('blockTimeSlot') == slot, 'block-time-slot-binding')
        reserves = [int(vaults[i]['amount'])-pool['accruedFees'+str(i)] for i in (0,1)]
        need(all(r >= 0 for r in reserves), 'vault-accrued-fees-exceed-balance')
        blockers = []
        if pool['status'] & 4: blockers.append('pool-swaps-disabled')
        if block_time < pool['openTime']: blockers.append('pool-not-open-at-snapshot-time')
        if not all(reserves): blockers.append('empty-effective-reserve')
        if any(m['freezeAuthority'] is not None for m in mints): blockers.append('mint-freeze-authority-present')
        if any(v['delegate'] is not None or v['closeAuthority'] is not None for v in vaults): blockers.append('vault-delegate-or-close-authority')
        result.update(state='pool-state-consistent',pool=pool_key,snapshotSlot=slot,blockTime=block_time,
                      poolRelationsMatched=True,authority=AUTHORITY,poolState=pool,configRatesMillionths=config,
                      mints=mints,vaults=vaults,effectiveReservesAtomic=list(map(str,reserves)),
                      programDataAddress=b58(program[4:]),observationInitialized=bool(observation[8]),
                      eligibilityBlockers=blockers,captureSha256=digest(capture),
                      stateAsOfMs=capture['finishedAtMs'],walletAccountsMatched=False)
        if packet is not None:
            a, p = packet['policy']['accounts'], packet['policy']
            orientation = 0 if a['inputMint'] == pool['mint0'] else 1
            expected = {'authority':AUTHORITY,'config':pool['config'],'observation':pool['observation'],
                        'inputMint':pool['mint'+str(orientation)],'outputMint':pool['mint'+str(1-orientation)],
                        'inputVault':pool['vault'+str(orientation)],'outputVault':pool['vault'+str(1-orientation)]}
            need(all(a[k] == v for k,v in expected.items()), 'policy-pool-role-mismatch')
            account(rows[8],SYSTEM,0)
            source, destination = token(rows[9],a['inputMint'],a['wallet']), token(rows[10],a['outputMint'],a['wallet'])
            need(all(t['delegate'] is None and t['closeAuthority'] is None for t in (source,destination)), 'wallet-authority-options', 'unsupported')
            need(int(source['amount']) >= int(p['amountIn']), 'insufficient-source-balance')
            need(int(destination['amount']) + int(p['minimumAmountOut']) <= U64, 'destination-minimum-overflow')
            need(reserves[1-orientation] >= int(p['minimumAmountOut']), 'insufficient-output-reserve-for-minimum')
            need(rows[8]['lamports'] >= int(p['maxTotalFeeLamports']), 'insufficient-native-fee-balance')
            bh = received(ev,'blockhash'); fee = received(ev,'fee')
            for item in (bh,fee):
                need(type(item) is dict and type(item.get('context')) is dict and
                     integer(item['context'].get('slot')) and item['context']['slot'] >= slot, 'preflight-context')
            need(bh.get('value') is True, 'blockhash-not-valid-at-capture', 'unavailable')
            need(integer(fee.get('value'),1), 'message-fee-unavailable', 'unavailable')
            need(fee['value'] == int(packet['feeAssertion']['lamports']) and fee['value'] <= int(p['maxTotalFeeLamports']), 'rpc-message-fee-mismatch')
            need(capture.get('messageSha256') == contract['wireMessageSha256'], 'capture-message-binding')
            result.update(state='policy-state-consistent',walletAccountsMatched=True,policySha256=contract['policySha256'],
                          wireMessageSha256=contract['wireMessageSha256'],sourceBalanceAtomic=source['amount'],
                          destinationBalanceAtomic=destination['amount'],rpcMessageFeeLamports=str(fee['value']),
                          rpcBlockhashValidAtCapture=True)
    except StateError as exc:
        result.update(state=exc.state,reason=exc.reason)
    except (Rejected,KeyError,TypeError,ValueError,IndexError):
        result.update(state='invalid-input',reason='malformed-capture')
    return result
