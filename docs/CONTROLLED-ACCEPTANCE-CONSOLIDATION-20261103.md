# Controlled devnet acceptance consolidation — November 3, 2026

This batch follows main `61017ff1017f8c0d62a82708555fa91af15fcbd2` (PR #72).
It combines three locally tested and host-accepted increments. Full regression
CI and an exact-head review must pass before merge. No production service,
scanner signal rule, study, notification or backup change is included.

## Accepted evidence

| Increment | Pinned source | Host evidence |
|---|---|---|
| Entry phase profiling | `c3a1d20c2d3ef0ce4e1a1c0a373afcacb6657f89` | Six checks, nineteen stages; November 3 05:04:56 UTC |
| Attempt-scoped verification reuse | `e5466724f13cffa0acd38f1155c8229c5faed3d9` | Seven checks, nineteen stages; 05:56:41 UTC |
| Controlled action interface | `71fc397144f1bcfcdc08f51de1020887709c91d4` | Eight boundary and nine lifecycle checks; 06:10:18 UTC; local status 06:10:19 UTC |

The connected interface report exercised entry, entry settlement, exit, lost
closure response and repeated closure recovery through the dispatcher. Each
synthetic transaction leg recorded one send and one signature within its original
deadline. Repeated closure recovery used no network requests, preserved journal
bytes and closure identity, and did not grant a new allocation. All temporary
ledgers were removed; no production wallet or real network was used.

The read-only status reported `local-scope-consistent`, closed historical source,
no occupied admission slot and no STOP flag. It made no network requests and did
not access a private key. It does not establish current balances, key availability
or readiness to spend.

## Timing and scope

The latest offline host sample measured entry 2,477.435 ms and exit 4,847.870 ms.
Receipt/accounting/closure measured 8,348.175 ms inclusively. These are synthetic
provider measurements, not real RPC/finality latency or profitability evidence.
The earlier live unsigned collection had 2,454 ms original-deadline headroom;
that check did not include durable admission, signing or send.

Attempt-scoped reuse verifies exactly identical successful signed bytes once per
bounded attempt. Changed bytes, parsing, source rereads, STOP, fee constraints and
original expiry guards still run. The scope is cleared on return or exception.
Default nested verification and recovery calls remain isolated.

Relevant increment validation passed 95, 101 and 17 checks/tests respectively
(with overlapping regressions); the last increment also passed both CI-partition
checks. Full CI retains all twelve groups and the ten-minute job limit.

## Next acceptance sequence

1. Merge only the reviewed CI-passing head.
2. Run one explicitly opted-in controlled devnet entry from the pinned merged
   source. Fresh collection must revalidate the real scope, funding and original
   deadlines. Caps must be provided explicitly; they cannot be replaced later.
3. Inspect its public report. An RPC acknowledgment is not finality. Unknown,
   failed, late or interrupted outcomes preserve journals; never repeat entry
   to retry. Choose status, acknowledgment recovery or entry settlement according
   to the recorded phase.
4. After entry receipt/accounting is verified, invoke a separate fresh exit.
   Then collect its receipt, reconcile balances and close the scoped allocation.
   Unknown outcomes stay held. No command automatically moves to the next stage.
5. Review measured real collection/sign/send/finality behavior and durable
   accounting before considering runtime integration. Successful devnet plumbing
   does not validate a selection rule or authorize mainnet funds.

The November 3 study capture is already complete per the user. Preserve November
5 and 6; review November 6 at 00:05 UTC / 01:05 Amsterdam. Economic qualification
remains a separate gate; the prior forward study did not establish profitability.
