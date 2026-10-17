# Execution simulation lab 1

This is a synthetic, persistent state-machine harness. It does not connect to Solana, sign transactions, access wallets, request routes or place orders. Passing these tests is an engineering milestone, not proof of executable trades or profitability.

The lab models a buy intent, uncertain submission, reconciled open position, sell intent, uncertain exit and reconciled close. SQLite transactions persist each accepted transition and its idempotency key. Duplicate identical events return the prior result; conflicting keys halt new buys. Unknown submission outcomes survive restart and cannot be resubmitted or cancelled as though they failed.

Terminal receipts require exact simulated transaction identity, USDC balance and token balance reconciliation. Partial quantities or unexpected external balances halt for investigation. Failed transactions can consume explicitly reconciled simulated fees. The stop control blocks new buys but permits position reconciliation and exits. Prepared quotes are rechecked for expiry at simulated submission.

Default **test-fixture** settings: 100 simulated USDC cash, 10 per entry, 20 principal exposure, two active positions, 20 cumulative gross realized loss, 0.10 fee allowance per operation, 15-second signal and five-second quote limits. Principal exposure excludes fees; cash reservations include buy fees. These are synthetic test parameters, not an approved live budget or a recommendation. Gross losses are not reset by gains. Active/unresolved positions retain exposure; an unknown loss cannot be assumed zero or resolved.

## Run without installation or production changes

```bash
cd ~/apps/solana-early-alpha-radar
python3 -E -s ~/apps/solana-radar-dev/execution-lab/run.py \
  --output "$PWD/radar-execution-simulation-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

The driver uses temporary `.sim.sqlite` ledgers and saves only a private report. Its three end-to-end scenarios cover unknown-buy restart recovery, mismatched balances, and a stop followed by exit and duplicate reconciliation. The broader regression suite additionally exercises limits, failed fees, expired quotes, uncertain exits and atomic rollback:

```bash
python3 -E -s -m unittest discover \
  -s ~/apps/solana-radar-dev/execution-lab -p 'test_*.py'
```

The engine can reopen its own marked simulation ledgers for tests. It refuses overwriting an existing ledger and does not accept production database filenames. There is no runtime service, automatic scheduler, private key input or live execution adapter.

## Still required before any funded test

A separately reviewed implementation must validate actual chain finality/expiry, RPC outages, blockhash handling, wallet isolation, real balances and token decimals, transaction simulation, spending approval, fee accounting, slippage, independent shutdown and operator recovery. The simulation ledger is not that implementation. No real stop-loss or exit guarantee exists here. Research evidence and explicit funded-test authorization remain separate gates.

## Separate public evidence reader

The [chain reader](../chain-reader/README.md) now provides bounded read-only RPC finality and balance evidence. It is not wired to this simulation ledger or to any production execution state. Missing/uncertain evidence never permits resubmission. Its addition does not implement the funded-test gates above.
