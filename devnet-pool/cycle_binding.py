"""Fixed cycle-2 identity shared by the sender and durable spending guard."""
from pathlib import Path
from contextvars import ContextVar
from functools import wraps
import copy
import hashlib
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'devnet-rehearsal'))
from core import check, directory, private_file, loads

CYCLE = 'controlled-cycle-0002'
VERSION = 'controlled-cycle-binding-1'
_OPERATION = ContextVar('cycle_evidence_operation', default=None)


def operation(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        token = _OPERATION.set({})
        try: return fn(*args, **kwargs)
        finally: _OPERATION.reset(token)
    return wrapped


def is_cycle(home): return Path(home).name == CYCLE


def root(home): return Path(home).parent if is_cycle(home) else Path(home)


def load(home, wallet=None, pool=None):
    # Import lazily: preparation replays the original sender's receipts.
    import cycle_preparation as c
    home = directory(home)
    check(is_cycle(home), 'cycle-directory-required')
    raw = private_file(home / 'preparation.json', c.LIMIT)
    seal = private_file(home / 'complete.json', 4096)
    stamp = hashlib.sha256(raw + seal).hexdigest()
    cache = _OPERATION.get(); key = str(home)
    if cache is not None and key in cache:
        previous, saved = cache[key]
        check(previous == stamp and wallet in (None, saved['wallet']) and pool in (None, saved['pool']),
              'cycle-preparation-changed-during-operation')
        return copy.deepcopy(saved)
    record = loads(raw)
    wallet = wallet or record['wallet']; pool = pool or record['pool']
    source, allocation = c.local(home.parent, wallet, pool)
    checked = c.existing(home.parent, wallet, pool, source, allocation)
    check(checked['state'] == 'prepared-not-executable', 'complete-cycle-preparation-required')
    binding = dict(format=VERSION, cycleId=CYCLE, preparationSha256=checked['preparationSha256'],
                priorEvidenceSha256=checked['priorEvidenceSha256'], wallet=wallet, pool=pool,
                historicalEntryAtomic=allocation['historicalEntryAtomic'],
                historicalSwapFeeLamports=allocation['historicalSwapFeeLamports'],
                nextEntryAtomic='1000', nextFeeAllowanceLamports='20000',
                cumulativeEntryCapAtomic='2000', cumulativeFeeCapLamports='40000',
                balances=record['balances'], accounts=source['scope']['accounts'])
    if cache is not None: cache[key] = (stamp, copy.deepcopy(binding))
    return binding


def continuity(capture, binding):
    from controlled_swap import swap
    check(binding['format'] == VERSION and binding['cycleId'] == CYCLE, 'cycle-binding-required')
    a = binding['accounts']; b = binding['balances']
    rows = dict(zip(capture['accountKeys'], capture['evidence']['accounts']['result']['value']))
    check(capture['evidence']['accounts']['result']['context']['slot'] >= b['slot']
          and str(rows[a['wallet']]['lamports']) == b['walletLamports']
          and swap.token(rows[a['source']], a['inputMint'], a['wallet'])['amount'] == b['originalTokenAtomic']
          and swap.token(rows[a['destination']], a['outputMint'], a['wallet'])['amount'] == b['backgroundAcquiredAtomic'],
          'cycle-starting-balances-changed')


def plan_matches(home, plan):
    binding = load(home, plan['scope']['accounts']['wallet'], plan['scope']['accounts']['pool']) if is_cycle(home) else None
    check(plan.get('cycleBinding') == binding, 'cycle-plan-binding')
    return binding
