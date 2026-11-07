# Expired signed exit: bounded evidence review

The November 7 chain report met its observation criteria: the exact saved
preparation was checked, four read-only devnet requests completed, the signature
status was absent, and the blockhash was invalid at finalized commitment. It did
not prove that the transaction never executed or authorize a replacement.

## This increment

`position-book/expired_exit_evidence_cli.py` checks the same saved signed exit
against eight bounded RPC reads, in this order:

1. Devnet genesis identity.
2. Saved blockhash validity at finalized commitment.
3. Finalized block height, bounded below by the validity response context.
4. Exact saved signature status, including transaction history search.
5. Exact saved transaction lookup, finalized and base64 encoded.
6. Wallet, source token account, acquired token account, and both mints in one
   finalized account snapshot, no older than the status response context.
7. That snapshot slot's block time.
8. Devnet genesis identity again.

It replays the signed preparation and local journals before and after the reads.
The account comparison uses the original entry roles and the exit preparation's
saved pre-execution accounts. It checks account bytes, wallet lamports, token
controls, held fees, and protected plus owned inventory. External credits or any
other balance changes remain visible blockers; they are not silently reconciled.

The observation is limited to a standard SPL token pair with five distinct
accounts. Wrapped native SOL is not supported by this check. Reads have a
30-second aggregate network budget, a 64 KiB response bound, and a 120-second
whole-operation acceptance bound. There are no retries or redirects. The tool
can inspect while STOP is present; it cannot sign, submit, change journals,
release reservations, or create a replacement generation.

## Interpreting output

- `expired-exit-evidence-observed` means the bounded observation completed.
- `expiry-evidence-consistent-held` means the blockhash is invalid, finalized
  height exceeds the saved last-valid block height, both signature and transaction
  lookups are absent, and all scoped accounts and inventory checks match.
- `expiry-evidence-needs-review-held` records explicit blockers. A returned
  transaction requires receipt reconciliation. Account changes require separate
  reconciliation, including apparently beneficial wallet credits.
- `expiry-evidence-unavailable` means validation or collection failed. No partial
  assessment is published as success. Preserve every journal.

Every result keeps `nonExecutionProven` and `recoveryAuthorized` false. A single
provider's absent lookup is not exhaustive historical proof; matching present
balances can hide intervening offsetting activity. No public report is accepted
as authority to change the private journals.

## Kali check

After checking out the pinned release commit provided in chat:

```bash
cd "$HOME/apps/solana-radar-dev"
python3 -E -s -W error::ResourceWarning -m unittest discover \
  -s position-book -p test_expired_exit_evidence.py -v
```

Then run the CLI from the radar project directory, using the exact wallet, pool,
private rehearsal directory, preparation SHA, and new output filename provided
in chat. Upload only the public output report. No Docker rebuild or scanner
restart is required.

## Following gate

Review the host evidence before designing any narrowly scoped retirement or
replacement transition. Any such transition must preserve the old signature and
receipt recovery path, bind fresh evidence and exact journal identity, prevent
duplicate sends and double release, and keep position inventory reserved until
proper reconciliation. This increment implements none of those state changes.

The scanner, quote observer, research sampling, frozen studies, and live trading
eligibility are unchanged. Passing engineering checks is not evidence of a
profitable trading strategy.

## Primary RPC semantics

- https://solana.com/docs/rpc/http/getblockheight
- https://solana.com/docs/rpc/http/gettransaction
- https://solana.com/docs/rpc/http/getsignaturestatuses
- https://solana.com/docs/rpc/http/isblockhashvalid
