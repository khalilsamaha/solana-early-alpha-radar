"""Public recorded token movements; never invents a prior trade intent."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'recorded-chain'))
from review import review
from reconcile import (EvidenceError, require, binding, token_maps, instructions,
                       TOKEN, SYSTEM, NATIVE, decode, U64)

FLAGS = {'reviewNetworkRequests': 0, 'transactionsSent': 0, 'intentProven': False,
         'executionApproved': False, 'resubmitAllowed': False, 'productionLedgerUpdated': False}
TOKEN_2022 = 'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'


def analyze(capture):
    identity = review(capture)
    result = {'format': 'recorded-token-flows-1', 'state': 'unknown', 'reason': None,
              'identity': identity, **FLAGS,
              'limitations': [
                  'Historical accounting only. No prior intent, expected output, fee cap or wallet ownership is inferred.',
                  'RPC reports cluster, finality, balances and inner instructions. Signatures authenticate the outer message, not those reports.',
                  'Only standard SPL transfers, CreateAccount plus InitializeAccount3, empty-account CloseAccount, and existing WSOL are understood.',
                  'ALT, Token-2022, mint/burn, wrap/unwrap, transient unrecorded accounts and delegated/multisig authorities are unsupported.',
                  'A consistent movement is not necessarily a swap, safe program behavior, executable quote or profit. No execution ledger is updated.']}
    try:
        if identity['state'] == 'signed-message-consistent-lookup-unverified':
            raise EvidenceError('unsupported', 'historical-lookup-resolution-unproven')
        require(identity['state'] == 'signed-transaction-consistent',
                identity['reason'] or 'identity-evidence-incomplete', identity['state'])
        tx = capture['evidence']['transactionJson']['result']; meta = tx['meta']
        _, keys, outer = binding(tx)
        pre, post = token_maps(meta, keys)
        accounts = set(pre) | set(post)
        require(bool(accounts), 'no-recorded-token-accounts', 'unknown')
        result['recordedTokenAccounts'] = len(accounts)
        rows = {}
        for account in accounts:
            a, b = pre.get(account), post.get(account)
            row = a or b
            require(row['programId'] == TOKEN, 'token-program-not-supported', 'unsupported')
            if a and b:
                require(all(a[k] == b[k] for k in ('owner','mint','programId','decimals')), 'token-identity-changed')
            rows[account] = row
        native_pre, native_post = meta['preBalances'], meta['postBalances']
        expected_native = [0] * len(keys); expected_native[0] = -meta['fee']
        if meta['err'] is not None:
            require(pre == post, 'failed-transaction-token-change')
            require(all(after-before == change for before,after,change in zip(native_pre,native_post,expected_native)),
                    'failed-transaction-not-fee-only')
            result.update(state='recorded-failure-fee-only', accountsChecked=len(accounts), feeLamports=str(meta['fee']))
            return result
        ops = instructions(meta, outer, keys)
        current = {a: pre[a]['amount'] if a in pre else 0 for a in accounts}
        opened = set(pre); created = set(); initialized = set(); closed = set()
        effects = []; funding = []; refunds = []
        for account in accounts:
            i = keys.index(account); row = rows[account]
            if row['mint'] == NATIVE:
                require(account in pre and account in post, 'wrapped-native-lifecycle-not-supported', 'unsupported')
                require(row['decimals'] == 9 and native_pre[i]-pre[account]['amount'] > 0 and
                        native_pre[i]-pre[account]['amount'] == native_post[i]-post[account]['amount'],
                        'wrapped-native-backing-mismatch')
        for order, op in enumerate(ops):
            program, data, ac = op['program'], op['data'], op['accounts']
            require(program != TOKEN_2022, 'token-program-not-supported', 'unsupported')
            if program == SYSTEM:
                require(len(data)==52 and data[:4]==bytes(4) and len(ac)==2,
                        'unsupported-system-operation', 'unsupported')
                payer, account = ac
                require(account in accounts and account not in pre and account not in created,
                        'unproved-or-repeated-creation', 'unknown')
                require(account != payer and native_pre[keys.index(account)] == 0 and
                        data[20:] == decode(TOKEN) and int.from_bytes(data[12:20],'little') == 165,
                        'creation-owner-space-or-prebalance-mismatch')
                amount = int.from_bytes(data[4:12],'little')
                require(amount > 0 and amount == native_post[keys.index(account)], 'creation-funding-mismatch')
                created.add(account)
                expected_native[keys.index(payer)] -= amount; expected_native[keys.index(account)] += amount
                funding.append({'account': account, 'payer': payer, 'lamports': str(amount)})
                continue
            if program != TOKEN:
                continue  # Outer router semantics are not audited; all balance changes still must reconcile.
            require(bool(data), 'empty-token-instruction', 'unsupported')
            tag = data[0]
            if tag == 18:
                require(len(data)==33 and len(ac)==2, 'unsupported-initialize-layout', 'unsupported')
                account, mint = ac
                require(account in created and account not in opened and account not in initialized,
                        'initialization-without-unique-creation', 'unknown')
                require(rows[account]['mint']==mint and data[1:]==decode(rows[account]['owner']),
                        'initialization-identity-mismatch')
                opened.add(account); initialized.add(account)
            elif tag == 9:
                require(len(data)==1 and len(ac)==3, 'unsupported-close-layout', 'unsupported')
                account, recipient, authority = ac
                require(account in pre and account not in post and account in opened and account not in closed,
                        'closure-endpoint-evidence-incomplete', 'unknown')
                require(rows[account]['mint'] != NATIVE, 'wrapped-native-lifecycle-not-supported', 'unsupported')
                require(authority == rows[account]['owner'], 'close-authority-not-supported', 'unsupported')
                require(current[account] == 0 and native_post[keys.index(account)] == 0 and recipient != account,
                        'closure-balance-mismatch')
                refund = native_pre[keys.index(account)]
                require(refund > 0, 'closure-refund-unavailable', 'unknown')
                opened.remove(account); closed.add(account)
                expected_native[keys.index(account)] -= refund; expected_native[keys.index(recipient)] += refund
                refunds.append({'account': account, 'recipient': recipient, 'lamports': str(refund)})
            elif tag in (3,12):
                checked = tag == 12
                require(len(data)==(10 if checked else 9) and len(ac)==(4 if checked else 3),
                        'unsupported-transfer-layout', 'unsupported')
                source, destination, authority = ac[0], ac[2 if checked else 1], ac[-1]
                require(source in opened and destination in opened, 'transfer-account-not-initialized-or-recorded', 'unknown')
                a,b = rows[source], rows[destination]
                require(all(a[k]==b[k] for k in ('mint','programId','decimals')), 'transfer-token-identity-mismatch')
                require(authority==a['owner'], 'transfer-authority-not-supported', 'unsupported')
                if checked:
                    require(ac[1]==a['mint'] and data[-1]==a['decimals'], 'checked-transfer-identity-mismatch')
                amount = int.from_bytes(data[1:9],'little')
                require(current[source] >= amount, 'transfer-intermediate-underflow')
                current[source] -= amount; current[destination] += amount
                require(current[destination] <= U64, 'transfer-intermediate-overflow')
                if a['mint']==NATIVE:
                    expected_native[keys.index(source)] -= amount; expected_native[keys.index(destination)] += amount
                effects.append({'order': order, 'source':source, 'destination':destination, 'mint':a['mint'],
                                'amountAtomic':str(amount), 'decimals':a['decimals'], 'selfTransfer':source==destination})
            else:
                raise EvidenceError('unsupported', 'unsupported-token-instruction')
        require(created == initialized == (set(post)-set(pre)), 'creation-evidence-incomplete', 'unknown')
        require(closed == (set(pre)-set(post)), 'closure-evidence-incomplete', 'unknown')
        require(all(current[a] == (post[a]['amount'] if a in post else 0) for a in accounts), 'transfer-flow-balance-mismatch')
        require(all(after-before == change for before,after,change in zip(native_pre,native_post,expected_native)),
                'unexplained-native-balance-change')
        result.update(state='recorded-token-flows-consistent', feeLamports=str(meta['fee']), transfers=effects,
                      accountFunding=funding, accountRefunds=refunds,
                      accounts=[{'account':a, 'mint':rows[a]['mint'], 'owner':rows[a]['owner'],
                                 'decimals':rows[a]['decimals'], 'preAtomic':str(pre[a]['amount']) if a in pre else None,
                                 'postAtomic':str(post[a]['amount']) if a in post else None,
                                 'lifecycle':'created' if a in created else 'closed' if a in closed else 'existing'}
                                for a in sorted(accounts)])
    except EvidenceError as e:
        result.update(state=e.state, reason=e.reason)
    except (ValueError,KeyError,TypeError,AttributeError,IndexError,OverflowError,RecursionError):
        result.update(state='invalid-input',reason='malformed-token-evidence')
    return result
