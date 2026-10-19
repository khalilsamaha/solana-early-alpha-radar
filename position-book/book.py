"""Offline signed-evidence position accounting. No signer, RPC or sender."""
import contextlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'token-reconciliation'))
from audit import audit
from journal import Journal, encoded
from wire import check
from reconcile import atomic, base58, digest, TOKEN, NATIVE

FLAGS = {'networkRequests': 0, 'transactionsSent': 0, 'executionApproved': False,
         'resubmitAllowed': False, 'productionLedgerUpdated': False}


class AtomicJournal(Journal):
    """Compose reservation and prior-intent changes in one outer SQLite commit."""
    @contextlib.contextmanager
    def transaction(self):
        if self.db.in_transaction:
            # Inner methods propagate errors; the outer transaction rolls everything back.
            yield
        else:
            with super().transaction():
                yield


def validate_policy(p):
    fields = {'format', 'network', 'wallet', 'quoteAccount', 'quoteMint', 'quoteDecimals',
              'initialQuoteAtomic', 'initialNativeLamports', 'maximumPrincipalAtomic',
              'maximumGrossLossAtomic', 'maximumTotalFeeLamports', 'maximumLegFeeLamports',
              'maximumIntentAgeMs'}
    check(isinstance(p, dict) and set(p) == fields and p['format'] == 'position-book-policy-1', 'policy-schema')
    check(p['network'] == 'devnet', 'devnet-labelled-evidence-only')
    for k in ('wallet', 'quoteAccount', 'quoteMint'): base58(p[k], 32)
    check(len({p['wallet'], p['quoteAccount'], p['quoteMint']}) == 3 and p['quoteMint'] != NATIVE, 'policy-identities')
    check(type(p['quoteDecimals']) is int and 0 <= p['quoteDecimals'] <= 18, 'policy-decimals')
    for k in fields - {'format','network','wallet','quoteAccount','quoteMint','quoteDecimals','maximumIntentAgeMs'}:
        check(0 < atomic(p[k]) < 2**63, 'policy-amount')
    check(atomic(p['maximumPrincipalAtomic']) <= atomic(p['initialQuoteAtomic']), 'principal-exceeds-cash')
    check(type(p['maximumIntentAgeMs']) is int and 1 <= p['maximumIntentAgeMs'] <= 15000, 'intent-age-cap')


class Book:
    def __init__(self, path, policy=None, clock=None):
        path = Path(path)
        existed = path.exists() or path.is_symlink()
        check(path.name.endswith('.positions.sqlite'), 'separate-position-filename-required')
        check(existed or policy is not None, 'book-not-found')
        if policy is not None: validate_policy(policy)
        self.j = AtomicJournal(path, clock=clock, create=policy is not None)
        self.db = self.j.db
        try:
            if not existed:
                with self.j.transaction():
                    self.db.execute('CREATE TABLE book (id INTEGER PRIMARY KEY CHECK(id=1), policy TEXT NOT NULL, cash TEXT NOT NULL, native TEXT NOT NULL, fees TEXT NOT NULL, gross_loss TEXT NOT NULL, stopped INTEGER NOT NULL, quarantined INTEGER NOT NULL, last_slot INTEGER NOT NULL)')
                    self.db.execute('CREATE TABLE positions (id TEXT PRIMARY KEY, state TEXT NOT NULL, principal TEXT NOT NULL, asset TEXT NOT NULL, quantity TEXT NOT NULL, entry_slot INTEGER, pnl TEXT)')
                    self.db.execute('CREATE TABLE legs (id TEXT PRIMARY KEY REFERENCES intents(id), position_id TEXT NOT NULL REFERENCES positions(id), side TEXT NOT NULL, final_identity TEXT)')
                    self.db.execute('INSERT INTO book VALUES (1,?,?,?,?,?,0,0,0)',
                        (encoded(policy), policy['initialQuoteAtomic'], policy['initialNativeLamports'], '0', '0'))
            row = self.meta()
            self.policy = json.loads(row['policy'])
            validate_policy(self.policy)
            check(policy is None or encoded(policy) == row['policy'], 'immutable-policy-conflict')
        except BaseException:
            self.close()
            raise

    def close(self): self.j.close()

    def meta(self):
        row = self.db.execute('SELECT * FROM book WHERE id=1').fetchone()
        check(row is not None, 'unrecognized-position-book')
        return row

    def position(self, pid):
        row = self.db.execute('SELECT * FROM positions WHERE id=?', (pid,)).fetchone()
        check(row is not None, 'position-not-found')
        return row

    def leg(self, lid):
        row = self.db.execute('SELECT * FROM legs WHERE id=?', (lid,)).fetchone()
        check(row is not None, 'leg-not-found')
        return row

    def contract(self, i):
        p, m = self.policy, self.meta()
        check(i['network'] == p['network'] and i['wallet'] == p['wallet'], 'wallet-or-network-conflict')
        check(int(i['walletPreLamports']) == int(m['native']), 'native-continuity-mismatch')
        check(0 < int(i['maximumFeeLamports']) <= int(p['maximumLegFeeLamports']), 'leg-fee-cap')
        check(int(i['maximumRentLamports']) == 0, 'rent-not-supported-in-position-book')
        check(all(i[s]['lifecycle'] == 'existing' and i[s]['mint'] != NATIVE for s in ('source','destination')), 'existing-nonnative-accounts-only')
        now = self.j.now()
        check(0 <= now-i['preparedAtMs'] <= p['maximumIntentAgeMs'], 'stale-intent')

    def quote(self, a):
        p = self.policy
        check(all(a[k] == v for k,v in {'account':p['quoteAccount'],'mint':p['quoteMint'],
              'decimals':p['quoteDecimals'],'programId':TOKEN}.items()), 'quote-identity-mismatch')
        check(int(a['preAmountAtomic']) == int(self.meta()['cash']), 'quote-continuity-mismatch')

    def reserve(self, pid, side, registration):
        check(isinstance(pid, str) and re.fullmatch('[a-zA-Z0-9_-]{1,80}', pid), 'position-id')
        check(side in ('entry','exit'), 'leg-side')
        with self.j.transaction():
            # Validates schema, signatures, exact message and duplicate signed identity.
            # Any later failed policy check rolls this insert back too.
            before = self.db.execute('SELECT 1 FROM intents WHERE id=?', (registration.get('logicalIntentId'),)).fetchone()
            self.j.register(registration)
            lid = registration['logicalIntentId']; i = registration['intent']
            if before:
                leg = self.leg(lid)
                check(leg['position_id'] == pid and leg['side'] == side, 'leg-binding-conflict')
                return self.status(pid)
            self.contract(i)
            m, p = self.meta(), self.policy
            check(not m['quarantined'], 'book-quarantined')
            fee = int(i['maximumFeeLamports'])
            if side == 'entry':
                check(not m['stopped'], 'entries-stopped')
                check(int(m['gross_loss']) < int(p['maximumGrossLossAtomic']), 'gross-loss-limit')
                check(self.db.execute("SELECT 1 FROM positions WHERE state NOT IN ('closed','entry-failed')").fetchone() is None, 'active-position-limit')
                check(self.db.execute('SELECT 1 FROM positions WHERE id=?',(pid,)).fetchone() is None, 'position-id-reused')
                self.quote(i['source'])
                principal = int(i['inputAtomic'])
                check(principal <= min(int(m['cash']),int(p['maximumPrincipalAtomic'])), 'principal-limit')
                check(int(i['destination']['preAmountAtomic']) == 0, 'position-account-not-empty')
                # Reserve one possible exit fee in addition to the entry fee.
                fee += int(p['maximumLegFeeLamports'])
                asset = {k:i['destination'][k] for k in ('account','mint','programId','decimals')}
                self.db.execute('INSERT INTO positions VALUES (?,?,?,?,?,NULL,NULL)',
                    (pid,'entry-prepared',str(principal),encoded(asset),'0'))
            else:
                pos = self.position(pid)
                check(pos['state'] == 'open', 'position-not-open')
                self.quote(i['destination'])
                asset = json.loads(pos['asset'])
                check(all(i['source'][k] == v for k,v in asset.items()), 'exit-asset-mismatch')
                check(int(i['source']['preAmountAtomic']) == int(i['inputAtomic']) == int(pos['quantity']) > 0, 'full-exit-quantity-required')
                self.db.execute("UPDATE positions SET state='exit-prepared' WHERE id=?",(pid,))
            check(int(m['native']) >= fee, 'native-fee-reserve')
            check(int(m['fees']) + fee <= int(p['maximumTotalFeeLamports']), 'cumulative-fee-limit')
            self.db.execute('INSERT INTO legs VALUES (?,?,?,NULL)',(lid,pid,side))
        return self.status(pid)

    def boundary(self, lid):
        with self.j.transaction():
            leg, row, m = self.leg(lid), self.j.row(lid), self.meta()
            pos = self.position(leg['position_id'])
            check(not m['quarantined'] and pos['state'] == leg['side']+'-prepared', 'position-boundary-state')
            check(leg['side'] == 'exit' or not m['stopped'], 'entries-stopped')
            self.contract(json.loads(row['intent']))
            self.j.mark_submission_boundary(lid)
            self.db.execute('UPDATE positions SET state=? WHERE id=?', (leg['side']+'-unknown',pos['id']))
        return self.status(pos['id'])

    def stop_entries(self):
        with self.j.transaction():
            self.db.execute('UPDATE book SET stopped=1 WHERE id=1')
        return self.status()

    def observe(self, lid, package):
        # Re-run full raw signed evidence validation. A previously generated summary
        # cannot advance a position. No inferred receipts or return calculations.
        check(len(encoded(package)) <= 4*1024*1024, 'evidence-cap')
        with self.j.transaction():
            leg, row = self.leg(lid), self.j.row(lid)
            pos = self.position(leg['position_id']); now = self.j.now()
            check(row['state'] != 'prepared', 'boundary-required')
            if row['state'] == 'quarantined': return self.status(pos['id'])
            result = audit(package)
            binding_ok = (isinstance(package,dict) and isinstance(package.get('bundle'),dict)
                and package['bundle'].get('intent') == json.loads(row['intent'])
                and result.get('wireSha256') == json.loads(row['wire'])['wireSha256'])
            success = result['state'] == 'signed-token-accounting-consistent'
            failed = result['state'] == 'finalized-failure-fee-only'
            unknown = result['state'] == 'unknown'
            identity = None
            if binding_ok and (success or failed):
                identity = digest({k:result[k] for k in ('state','slot','wireSha256','tokenAccounts','native')})
            conflict = not binding_ok or not (success or failed or unknown)
            if leg['final_identity']:
                if unknown and binding_ok: return self.status(pos['id'])
                if identity == leg['final_identity']: return self.status(pos['id'])
                conflict = True
            if not conflict and unknown:
                # Preserve unresolved reservations. Identical observations need not grow the journal.
                eh = digest(package)
                if row['evidence_hash'] != eh:
                    self.j.event(lid,now,'position-unknown',{'evidenceSha256':eh})
                    self.db.execute('UPDATE intents SET evidence_hash=? WHERE id=?',(eh,lid))
                return self.status(pos['id'])
            if not conflict:
                conflict = (result['slot'] <= self.meta()['last_slot'] or
                    pos['state'] != leg['side']+'-unknown' or
                    (leg['side']=='exit' and result['slot'] <= pos['entry_slot']))
            if conflict:
                self.db.execute('UPDATE book SET quarantined=1 WHERE id=1')
                self.db.execute("UPDATE positions SET state='quarantined' WHERE id=?",(pos['id'],))
                self.db.execute("UPDATE intents SET state='quarantined' WHERE id=?",(lid,))
                self.j.event(lid,now,'position-quarantined',{'evidenceSha256':digest(package)})
                return self.status(pos['id'])
            m = self.meta(); fee = int(result['native']['feeLamports'])
            check(result['native']['rentSpentLamports'] == result['native']['rentRefundedLamports'] == '0', 'unexpected-rent')
            cash = int(m['cash']); quantity = int(pos['quantity']); pnl = pos['pnl']
            loss = int(m['gross_loss']); entry_slot = pos['entry_slot']
            if failed:
                state = 'entry-failed' if leg['side']=='entry' else 'open'
            elif leg['side']=='entry':
                cash -= int(pos['principal'])
                quantity = int(result['tokenAccounts']['destination']['postAtomic'])
                entry_slot, state = result['slot'], 'open'
            else:
                returned = int(result['tokenAccounts']['destination']['deltaAtomic'])
                cash += returned; quantity = 0; state = 'closed'
                pnl = str(returned-int(pos['principal']))
                loss += max(0,-int(pnl))
            self.db.execute('UPDATE book SET cash=?,native=?,fees=?,gross_loss=?,last_slot=? WHERE id=1',
                (str(cash),str(int(m['native'])-fee),str(int(m['fees'])+fee),str(loss),result['slot']))
            self.db.execute('UPDATE positions SET state=?,quantity=?,entry_slot=?,pnl=? WHERE id=?',
                (state,str(quantity),entry_slot,pnl,pos['id']))
            self.db.execute('UPDATE legs SET final_identity=? WHERE id=?',(identity,lid))
            self.db.execute('UPDATE intents SET state=?,final_hash=? WHERE id=?',
                ('reconciled' if success else 'failed-fee-only',identity,lid))
            self.j.event(lid,now,'position-reconciled',{'finalIdentity':identity,'state':state})
        return self.status(pos['id'])

    def status(self, pid=None):
        with self.j.transaction():
            return self._status(pid)

    def _status(self, pid=None):
        m = self.meta()
        rows = self.db.execute('SELECT * FROM positions ORDER BY id').fetchall()
        pending = self.db.execute("SELECT i.intent FROM intents i JOIN legs l ON l.id=i.id WHERE i.state IN ('prepared','submission-unknown','quarantined')").fetchall()
        reserved_fee = sum(int(json.loads(r[0])['maximumFeeLamports']) for r in pending)
        reserved_fee += sum(int(self.policy['maximumLegFeeLamports']) for r in rows if r['state'] in ('entry-prepared','entry-unknown','open'))
        reserved_cash = sum(int(r['principal']) for r in rows if r['state'] in ('entry-prepared','entry-unknown'))
        exposure = sum(int(r['principal']) for r in rows if r['state'] not in ('closed','entry-failed'))
        result = {'format':'position-book-status-1','mode':'offline-signed-evidence',
            'lastReconciledSlot':m['last_slot'],'policySha256':digest(self.policy),'entriesStopped':bool(m['stopped']),
            'quarantined':bool(m['quarantined']),'accountingUsable':not bool(m['quarantined']),
            'lastReconciledQuoteAtomic':m['cash'],'lastReconciledNativeLamports':m['native'],
            'reservedQuoteAtomic':str(reserved_cash),'principalExposureAtomic':str(exposure),
            'reservedFeeLamports':str(reserved_fee),'feesSpentLamports':m['fees'],
            'feeBudgetRemainingLamports':str(int(self.policy['maximumTotalFeeLamports'])-int(m['fees'])),
            'feeReserveCovered':not bool(m['quarantined']) and min(int(m['native']),
                int(self.policy['maximumTotalFeeLamports'])-int(m['fees'])) >= reserved_fee,
            'cumulativeGrossLossAtomic':m['gross_loss'],
            'positions':[dict(r) for r in rows if pid is None or r['id']==pid],**FLAGS}
        return result
