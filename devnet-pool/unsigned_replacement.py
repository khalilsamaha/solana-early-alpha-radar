"""One explicit replacement of the refused, expired and provably unsigned cycle-2 entry.

Preparation has no key/network capability. Rename preserves the original files;
the existing spending ledger retains the principal and full round-trip allowance.
"""
import copy
import hashlib
import os
import re
import time
from pathlib import Path
import cycle_binding as binding
import cycle_preparation as c
import cycle_reservation_cli as audit
from core import check, directory, private_file, loads, write_new, sync_directory

VERSION='unsigned-cycle-replacement-1'
ARCHIVE='refused-unsigned-entry-v1'
INTENT='unsigned-replacement.json'
SEAL='unsigned-replacement-ready.json'
FILES=(ARCHIVE,INTENT,SEAL)
digest=c.controlled.digest


def exists(home):return os.path.lexists(Path(home)/INTENT)


def evidence(child):
    directory(child)
    check({p.name for p in child.iterdir()} == set(audit.FILES),'replacement-unsigned-files-required')
    raw={name:private_file(child/name,limit) for name,limit in audit.FILES.items()}
    return {name:hashlib.sha256(v).hexdigest() for name,v in raw.items()}, {name:loads(v) for name,v in raw.items()}


def manifest(home, *, archived=True):
    m=loads(private_file(home/INTENT,32768))
    check(set(m)=={'format','cycleId','preparationSha256','evidenceSha256','files','oldEntry','oldLedgerHash','oldLedgerCount','approvedAtMs'},
          'replacement-manifest-shape')
    b=binding.load(home)
    check(m['format']==VERSION and m['cycleId']==binding.CYCLE and m['preparationSha256']==b['preparationSha256']
          and type(m['approvedAtMs']) is int and m['approvedAtMs']<=time.time_ns()//1000000
          and m['oldLedgerCount']==1 and re.fullmatch('[a-f0-9]{64}',m['oldLedgerHash']), 'replacement-manifest-identity')
    hashes,values=evidence(home/(ARCHIVE if archived else c.submit.CHILD))
    check(m['files']==hashes and m['evidenceSha256']==digest(hashes),'replacement-archive-changed')
    old=m['oldEntry'];plan=values['plan.json'];capture=values['preflight.json'];request=values['signing-request.json']
    check(set(old)=={'contract','reservedAtMs','signed','boundaryAtMs','receipt'} and old['signed'] is None
          and old['boundaryAtMs'] is None and old['receipt'] is None, 'replacement-old-entry-not-unsigned')
    contract=old['contract']
    check(plan.get('cycleBinding')==b and 'unsignedReplacementSha256' not in plan
          and contract['planSha256']==digest(plan) and contract['preflightSha256']==digest(capture)
          and contract['scopeSha256']==digest(plan['scope']) and capture['packet']==plan['packet']
          and request['planSha256']==digest(plan) and request['preflightSha256']==digest(capture)
          and values['execution.json']['planSha256']==digest(plan)
          and values['spending-reservation.json']==dict(format=c.submit.spend_guard.VERSION,side='entry',planSha256=digest(plan)),
          'replacement-old-contract-binding')
    check(values['failure.json'].get('phase')=='signing' and values['failure.json'].get('reason')=='execution-validation-or-transport-incomplete',
          'replacement-signing-refusal-required')
    check(type(request['expiresAtMs']) is int and type(plan['packet']['policy']['expiresAtMs']) is int
          and m['approvedAtMs']>=max(request['expiresAtMs'],plan['packet']['policy']['expiresAtMs'])
          and contract['expiresAtMs']==plan['packet']['policy']['expiresAtMs'],'replacement-old-plan-not-expired')
    return m,values


def ready(home):
    m,values=manifest(home)
    seal=loads(private_file(home/SEAL,4096))
    check(seal==dict(format=VERSION,manifestSha256=digest(m)),'replacement-not-ready')
    return m,values


def public(home, *, changed=False):
    m,_=ready(home)
    with c.submit.spend_guard.Guard(home) as g:
        state=g.read()[0];summary=g.summary()
    check(state and state.get('unsignedReplacement',{}).get('manifestSha256')==digest(m),'replacement-authorization-missing')
    return dict(format=VERSION,state='unsigned-replacement-prepared',cycleId=binding.CYCLE,
        preparationSha256=m['preparationSha256'],evidenceSha256=m['evidenceSha256'],manifestSha256=digest(m),
        originalJournalPreserved=True,preparationChanged=changed,spendingGuard=summary,
        networkRequests=0,privateKeyAccessed=False,signaturesCreated=0,transactionsSent=0,executionApproved=False,
        automaticRetryAllowed=False,mainnetEnabled=False,
        limitations=['One explicit fresh entry only; the old reservation is never released.',
                    'Local file ownership and the shared lock are trusted; this is not a wallet-wide spending control.',
                    'Preparation does not refresh balances or authorize a mainnet transaction.'])


@binding.operation
def prepare(home,wallet,pool,expected_preparation,expected_evidence):
    for value in (expected_preparation,expected_evidence):check(type(value) is str and re.fullmatch('[a-f0-9]{64}',value),'replacement-expected-hash')
    # Initial independent signer-policy audit occurs under the same root lock.
    # The subsequent locked section rechecks every file hash before committing.
    if not exists(Path(home)/binding.CYCLE):
        checked=audit.inspect(home,wallet,pool)
        check(checked['preparationSha256']==expected_preparation and checked['evidenceSha256']==expected_evidence,
              'replacement-approved-evidence-mismatch')
    with c.controlled.source_lock(home,wallet) as root:
        check(not c.submit.swap.stop(root),'stop-requested')
        cycle=directory(root/binding.CYCLE);b=binding.load(cycle,wallet,pool)
        check(b['preparationSha256']==expected_preparation,'replacement-approved-preparation-mismatch')
        current=cycle/c.submit.CHILD;archive=cycle/ARCHIVE
        changed=False
        if not exists(cycle):
            check(not os.path.lexists(archive) and not os.path.lexists(cycle/SEAL),'unexpected-replacement-artifacts')
            hashes,values=evidence(current)
            check(digest(hashes)==expected_evidence,'replacement-approved-evidence-mismatch')
            with c.submit.spend_guard.Guard(cycle) as g:
                state,count,head,_=g.read()
                check(state and not state['quarantined'] and count==1 and set(state['legs'])=={'entry'}
                      and 'unsignedReplacement' not in state,'replacement-initial-reservation-required')
                old=state['legs']['entry']
                check(old['signed'] is None and old['boundaryAtMs'] is None and old['receipt'] is None,'replacement-old-entry-not-unsigned')
            now=time.time_ns()//1000000
            check(now>=max(values['plan.json']['packet']['policy']['expiresAtMs'],values['signing-request.json']['expiresAtMs']),
                  'replacement-old-plan-not-expired')
            m=dict(format=VERSION,cycleId=binding.CYCLE,preparationSha256=expected_preparation,evidenceSha256=expected_evidence,
                   files=hashes,oldEntry=copy.deepcopy(old),oldLedgerHash=head,oldLedgerCount=count,approvedAtMs=now)
            write_new(cycle/INTENT,m);changed=True
        m,_=manifest(cycle,archived=os.path.lexists(archive))
        check(m['preparationSha256']==expected_preparation and m['evidenceSha256']==expected_evidence,'replacement-approved-evidence-mismatch')
        if os.path.lexists(cycle/SEAL):return public(cycle)
        if not os.path.lexists(archive):
            os.rename(current,archive);sync_directory(cycle);changed=True
        else:check(not os.path.lexists(current),'replacement-incomplete-with-new-journal')
        manifest(cycle)
        with c.submit.spend_guard.Guard(cycle) as g:g.authorize_unsigned_replacement(m)
        write_new(cycle/SEAL,dict(format=VERSION,manifestSha256=digest(m)))
        return public(cycle,changed=True)
