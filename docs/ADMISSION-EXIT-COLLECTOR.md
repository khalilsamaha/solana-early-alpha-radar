# Bounded admission-owned exit collection — 31 October 2026

Host acceptance: all 19 cases and flags matched at 06:05:55 UTC on October 31.

This increment connects the existing raw exit validator to fresh public devnet
observations for an already-accounted entry. It is an internal read-only collector,
not a production command. The portable CLI exposes only synthetic offline checks.

## What it validates

- Replays the collected entry receipt and same-ledger accounting before RPC.
- Uses only the acquired token delta, reverses the original accounts/mints/vaults,
  and retains the original per-exit fee cap and all other held commitments.
- Holds the cooperating wallet lock and uses read-only journal connections.
- Refuses any existing exit preparation, even expired: no replacement, provenance
  upgrade, deadline refresh or automatic retry.
- Makes at most twenty fixed devnet requests: initial pool/deployment (six), fresh
  unsigned packet/fee (four), account/deployment/fee checks (eight), then one
  unsigned simulation and final genesis check (two).
- Checks STOP and the original ten-second wall-clock budget before every request;
  final local validation also counts against the deadline. Existing bounded
  response readers and the shared thirty-second monotonic cap still apply.
- Replays exact quote, account funding and simulation effects, then verifies the
  admission identity and historical source again before emitting private evidence.

The private in-process envelope binds raw captures, packet construction, request
parameter hashes, entry-accounting identity and the original deadline. Its public
summary contains no wire or raw provider errors. Provenance describes local
collection; it is not a cryptographic attestation by the RPC provider.

## Boundaries and next integration

This collector does **not** write the exit preparation. Its provenance is explicitly
`durable: false`, and all signing/submission flags remain false. The [collected preparation increment](COLLECTED-EXIT-PREPARATION.md) now implements
atomic persistence and replay of the collected envelope in the same admission,
rechecking identity and expiry under the lock. Public reports must never become
signing capabilities, and legacy raw preparations must not acquire provenance by
assertion. Restricted signing, durable send/recovery, final receipts/residuals and
allocation release remain subsequent gates.

No scanner, observer, Telegram, backup, sampling or fixed-study configuration is
changed. No existing devnet cycle is reopened. This is engineering evidence, not
profitability evidence or funded-pilot approval.

## Kali acceptance

Use the pinned commit supplied in chat; fetching this source does not deploy it.
From `~/apps/solana-early-alpha-radar`, run:

```bash
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/admission_exit_capture_cli.py" \
  --output "$PWD/radar-exit-collector-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, 19 cases. The exercise uses fake HTTP and temporary
ledgers, blocks sockets and private signing, preserves source/admission bytes and
checks both successful collection and refusal paths. Upload only the public report.
The controlled live admission path remains unconnected; no live collection command
is provided in this increment.
