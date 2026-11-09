# Successor post-accounting balances

The original exit balance collector is tied to first-generation accounting.
This increment supplies the separate successor context while reusing its fixed
four-request transport, account validation and ten-second freshness contract.
The original collector and deadlines are unchanged.

The internal collector requires an injected provider and exact successor hash.
There is no default live provider, public observation command, imported report or
execution mode. Only usable durable successor accounting with zero owned residual
can begin network observation. STOP, missing accounting, failed exits, wrong
generations and source conflicts block it.

Under a source lock and a read-only SQLite snapshot, the context replays the
successor, retirement, signing, backend acknowledgment, receipt and accounting.
The current source must still have the exact bound closed cycle and no separate
held commitments, before and after observation; historical replay is not enough.
Expected wallet and token post-state comes from the successor's own pre-state and
validated receipt effects. The five accounts are the wallet, source/acquired
token accounts and their two mints. Native-token accounts remain unsupported.

The request sequence is exactly `getGenesisHash`, `getMultipleAccounts`,
`getBlockTime`, `getGenesisHash`, using the fixed devnet endpoint, finalized account
commitment and a minimum context slot at least the receipt slot. Response byte
limits, no redirects/retries, unchanged account controls and the original
30-second chain-age bound remain enforced. Native funds must cover all remaining
held fees, including retired exposure. Any unexplained change, including a
deposit, blocks the result.

Freshness includes final source replay, validation, snapshot/database close and
source-lock exit. Each request timeout is clipped to both the ten-second window
and the remaining 120-second whole-operation budget. A late or failed close cannot
leave a successful summary. No capture or accounting is persisted by observation.

`successor-balances-match-held` is as-of provider evidence only. It does not prove
the retired attempt never executed, release its fee exposure, close the position,
establish future spendability or permit a new entry. The remaining retired
exposure is reported explicitly. It cannot be erased merely to finish E0.

## Offline Kali acceptance

Use the pinned development commit and run
`python3 -B -E -s -W error::ResourceWarning position-book/successor_balance_cli.py --output NEW.json.gz`.
The nine connected cases build synthetic post-state independently from raw
receipt arrays. They cover matching balances, unavailable/failed accounting,
wrong generation/no provider, token/native/mint drift, missing accounts,
cluster/slot/chain-time/provider faults, STOP, validation/close expiry, writer
exclusion, changed current source commitments and operation-clipped timeouts. Journals, operational keys and real RPC
are untouched by the CLI.

This is an E0 increment, not full phase acceptance or an operational balance
report. Remaining closure design must retain or validly reconcile retired
exposure; operational execution and complete-path timing remain separate gates.
