# Fresh post-exit balance reconciliation — October 31, 2026

The accepted receipt accounting establishes historical effects. This increment
checks whether a fresh finalized account snapshot still matches those effects.
It is a read-only internal collector, not a release transaction or new allocation.
Its only public CLI is an offline synthetic host check.

## What it verifies

Before requesting anything, the collector replays the existing admission, exit
signing/submission, collected receipt and saved accounting. It requires a successful
flat exit with zero owned acquired-token residual; failed exits remain held.
Wallet/pool, exact accounts, mints and accounting identity come from local journals.
The original controlled-cycle source must also remain closed, with zero held
commitments and the same ledger/cycle identities, before and after collection.
No public report or caller-selected account list is accepted as authority.

Four fixed requests go to the devnet endpoint, without redirects or retries:

1. `getGenesisHash` checks cluster identity.
2. `getMultipleAccounts` reads wallet, source token account, acquired token account
   and both mints in one finalized batch, with the receipt slot as `minContextSlot`.
3. `getBlockTime` checks the returned snapshot slot against the observation clock.
4. `getGenesisHash` checks cluster identity again.

The batch must be at least as recent as the exit receipt. Block time must be no
more than 30 seconds old or two seconds ahead of the capture start. The complete
observation, including final local source replay, has a ten-second budget checked
against wall and monotonic clocks. Each response is capped at 32 KiB; total response
and private capture limits are 64 KiB. Slow responses, malformed envelopes,
provider errors and unavailable accounts fail closed without retries.

Native wallet funds must equal the prepared pre-exit balance minus the verified
exit fee and still cover retained fee commitments. Source/acquired token balances
must equal the receipt post-balances. Token account owner, authority, state, rent
lamports and all non-amount bytes must remain consistent with preparation. Delegates
or close authorities are rejected. Mint bytes and lamports must remain unchanged.
Existing standard SPL accounts only; native/WSOL routes are unsupported here.

Any unexplained difference blocks reconciliation—including an incoming deposit.
A legitimate deposit needs separate explicit reconciliation; this tool does not
silently claim it as proceeds or overwrite history. Equal balances prove only
as-of consistency, not absence of intervening activity that nets to zero.

## Output and integration boundary

`exit-balances-match-held` means the scoped snapshot matches the verified receipt
and prepared account state. A bounded private in-process capture can be handed to
a future atomic closure integration, which must revalidate identity, clocks and
freshness at its own commit boundary. Public summaries carry no such authority.
A slow evidence consumer cannot turn an expired observation into a successful
collector result.

No database write, new signature, transaction, reservation release, backup change,
scanner change, quote-policy change or study evaluation occurs. All funds remain
held. A local lock coordinates cooperating tools but cannot prevent external wallet
transactions; RPC evidence is not independent cryptographic chain verification.
This gate does not establish wallet-wide solvency or future spendability.

## Validation

Nine targeted local tests passed: eight collector tests, including its 18-case
portable CLI, plus the full-source signed-exit/accounting/balance/isolated-restore
integration. Checks cover changed source commitments, read-only files, late replies,
STOP, source changes during collection, invalid clocks, altered private evidence,
wrong request order, oversized/malformed replies and public-output restrictions.
The host check remains pending. Synthetic clocks do not prove live deadline performance.

## Host check

Use the exact branch and commit supplied in chat, then run:

```bash
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/exit_balance_cli.py" \
  --output "$PWD/radar-exit-balance-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, 18 cases. All RPC responses and ledgers in this
exercise are synthetic/disposable; no real network, wallet key or runtime is used.
No Docker rebuild or service restart is needed. Upload only the public report.

After acceptance, the next integration is durable scoped closure under the same
ledger writer reservation, with receipt/accounting identity replay, fresh evidence
at commit, expiry/STOP handling and isolated restore verification. Global fund
reuse and another execution remain separate from closure of this scoped record.
The original live timing gate also remains open.
