# Position accounting release — 19 October 2026

The devnet lifecycle and recovery host gates passed. At 04:12 UTC the report recorded one send and finalized success at slot 512673362. Independent offline reconstruction verified the exact seven-instruction message, all three signatures and the wire hash. The wallet moved from 9,995,000 to 9,980,000 test lamports: a 15,000-lamport fee. Both temporary accounts ended at zero. Intermediate token balances were transient and were not directly recorded.

The 04:18:02 UTC recovery report preserved the exact original intent, simulation and finalized receipt, with one durable boundary, zero new sends and zero network requests. This proves fresh-process local terminal recovery, not a second independent consensus observation or a physical power-loss test. The separate ten-case synthetic lifecycle report also reproduced exactly.

## What this release adds

`position-book` joins independently signed entry and exit evidence to a persistent position. It reserves principal and fee capacity before the recorded submission boundary, refuses duplicate boundaries, retains unknown outcomes, reconciles failed fees, and closes a full position only after matching finalized evidence. Entry stop, principal cap, cumulative fee cap, loss circuit breaker and contradiction quarantine persist across reopening. Raw evidence is revalidated; reports are not accepted as fill authority.

The supported first scope is existing nonnative standard token accounts, one position at a time. This deliberately integrates the already tested standard-token accounting path. The just-proven atomic WSOL lifecycle remains a separate fixed contract. No code connects either component to a generic router or production sender yet. [Detailed boundaries and accounting](../position-book/README.md).

## Host command

Fetch the release branch and select the exact commit provided in the accompanying chat, then:

```bash
cd ~/apps/solana-early-alpha-radar
python3 -E -s ~/apps/solana-radar-dev/position-book/cli.py \
  --output "$PWD/radar-position-check-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

Expected: ten synthetic cases pass, no network requests or transactions, temporary ledgers removed. Upload the generated report. No Docker rebuild, service restart or wallet/faucet action is needed. Scanner, quote observer, frozen research protocol, notifications and Backblaze are untouched.

## Next gates

1. Replay the host position self-check and keep the forward evidence collection running.
2. Validate a specifically supported router/message shape, including its economic limits before signing, with captured/simulated evidence. Do not substitute a positive quote or matching net balances for router validation.
3. Integrate these checks with a bounded devnet multi-transaction workflow and independent recovery/stop controls before any funded execution adapter.
4. Evaluate the frozen strategy protocol independently. Engineering success does not resolve the latest strategy-readiness failures or demonstrate profit.

The project has completed a real controlled devnet token lifecycle and terminal recovery. This release builds the accounting layer needed for separate entry/exit transactions. A real-money date remains unsupported by the evidence; no funded pilot is enabled here.

Validation: all 895 local regression tests passed (612 Python and 283 Node), including 32 new position-book tests. The ten-case host self-check is a separate deployment-environment verification and remains pending. The source manifest records this release’s files; GitHub CI runs the complete regression suite.
