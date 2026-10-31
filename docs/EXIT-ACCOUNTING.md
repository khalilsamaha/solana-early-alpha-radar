# Collected exit receipt accounting — October 31, 2026

The one-send exit submission report passed all 24 synthetic host cases at
2026-10-31 18:37:40 UTC. This increment adds same-ledger accounting from the saved
collector's raw exit receipts. It performs no RPC, signing, sending, wallet-wide
allocation or release. Its public CLI accepts no report, wallet or execution input.

## Receipt evidence required

The reviewer replays the original admission, collected entry accounting, immutable
exit preparation, signing boundary and one-send boundary. It derives the reverse
receipt intent from the exact packet and raw prepared accounts: wallet, mint and
account roles, decimals, pre-balances, quantity, minimum output and fee/rent caps.
It checks the saved wire's signature and canonical message through the existing
receipt auditor. Public summaries are never accepted as receipt authority.

Only genesis-bound captures of the original signature can advance accounting.
Finality headers alone do not establish token or native effects. Successful
receipts must show the exact two admitted vault transfers, owned input quantity,
minimum output, pre/post token conservation and fee-only native wallet change.
Rent changes and unsupported token/account operations are refused. Failed exits
must show no token fill and only their actual transaction fee.

The record separates:

- acquired quantity before exit, quantity spent and owned residual;
- protected inventory that existed outside this exit's allocation;
- returned source tokens, held pending final reconciliation;
- entry and exit fees paid, remaining attempt budgets and unused fee allowances.

The source-token proceeds-minus-entry-principal field is in atomic units of that
same mint. It is not a USD result or net profit; native SOL fees remain separately
accounted and no conversion or executable valuation is inferred.

## Atomicity and recovery

Source replay uses a separate read-only connection while the admission database's
writer reservation is held. The small accounting record and its identity commit
atomically, subject to the existing database size cap. Repeated applications never
reapply token changes or fees. Identical duplicate terminal captures preserve the
first accepted capture identity. Conflicting or altered evidence makes existing
accounting unusable without rewriting history or freeing commitments.

STOP and expiry do not hide already-observed effects. The private snapshot verifier
replays the saved receipt and accounting, including rehashed-tamper checks. Older
snapshots without exit accounting keep their existing projection. No backup service,
cloud settings, notification rules, scanner or quote sampling changes are made.

## States and remaining gate

| State | Meaning | Funds available for a new entry |
| --- | --- | --- |
| `exit-accounting-pending` | No sufficiently complete collected receipt | No |
| `exit-position-flat-held` | Receipt accounts for spending the owned acquired quantity; proceeds/unused fees remain held | No |
| `exit-failed-inventory-held` | Failed receipt accounts for fees; acquired inventory remains held | No |
| `quarantined` | Conflicting or invalid evidence | No |

Receipt residual accounting is historical. It does not establish current account
balances, custody of unrelated funds or present spendability. The next gate must
bind fresh account evidence and any unexplained movements to final allocation
reconciliation before release. It must preserve unknown exposure and prohibit
release after a failed exit with residual inventory. No new cycle is authorized.
Live timing acceptance within the original deadline also remains outstanding;
the synthetic integration tests do not replace it.

## Local validation

All 27 targeted tests passed: seven accounting tests (including the 15-case
portable CLI), one full-source signing/receipt/isolated-restore integration test,
and 19 existing recovery regression tests. The attached preceding transport
report was also replayed: all 24 cases and flags matched exactly. Source hygiene
and whitespace checks passed. The new accounting host report remains pending.

## Kali exercise

After fetching the pinned source from chat:

```bash
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/exit_accounting_cli.py" \
  --output "$PWD/radar-exit-accounting-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, 15 cases. This exercises temporary ledgers,
public pre-signed fixtures and synthetic RPC receipts, with zero real network
requests, wallet key access, new signatures or transactions. Upload the public
report. No Docker rebuild or service restart is needed.

The availability confirmation remains fixed: preserve November 1, 3, 5 and 6,
with the final capture at or after November 6 00:05 UTC / 01:05 Amsterdam before
running `availability-study/review.sh`. Keep every capture and stay below a
72-hour gap; no early evaluation or model refitting is added.
