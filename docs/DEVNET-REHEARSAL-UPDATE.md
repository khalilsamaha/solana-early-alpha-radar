# Devnet preparation and recovery — 18 October 2026

## Evidence reviewed

The supplied lookup report replayed exactly: 14 resolved addresses across two lookup tables matched current account bytes. One table was extended after the recorded transaction, so historical state remains unproven. This does not relax the intent journal's ALT admission rules.

The supplied recovery capture showed readiness HTTP 200, an active quote observer, polling and enabled timers. These establish the state at capture, not uninterrupted market coverage or successful cloud backups.

The user confirms Kali itself rebooted and Healthchecks.io sent an alert during approximately three hours offline. The supplied capture nevertheless reports a 5 September host boot and scanner/observer processes started on 16 October. Preserve both the user's account and the conflicting telemetry. Exact outage bounds and the reason for that mismatch remain unresolved; do not relabel this as a network-only or suspend event. Research outcomes crossing the interruption must retain missing/gapped status.

## Release scope

Added `devnet-rehearsal`, a standalone dedicated-wallet preparation tool. It includes:

- Offline synthetic self-check, with temporary local keys removed after use.
- New private devnet wallet initialization with no import or overwrite.
- Separate restricted signer accepting only a one-lamport System self-transfer.
- Durable intent-before-sign and signed-bytes-before-simulation commits.
- Exclusive session locking, one-plan limit and abrupt-stop recovery tests.
- Explicit bounded signed simulation with cluster, fee and same-simulation balance checks.
- Public reports that exclude keys, signed transaction bytes and arbitrary provider errors.

No broadcaster, airdrop, token swap, mainnet option, production ledger or automatic retry is included. The scanner, observer, alerts, sampling budgets, forward protocol and backup configuration are unchanged. First host commands run the offline check and initialize a dedicated wallet only. Full commands and recovery instructions: [devnet rehearsal README](../devnet-rehearsal/README.md).

## Roadmap position

Execution engineering has moved from offline receipt/intent checking and public recorded-chain validation to local key/signature preparation. Host initialization and live signed simulation remain to be verified. The next release can add a narrowly controlled devnet submission boundary with bounded polling, expiry handling and preserved unknown outcomes; token lifecycle and independent stop controls follow.

The strategy track remains separate. The latest reviewed forward audit had 166 compatible watches across two UTC days and failed the registered fitting guards. There is no new strategy result in this engineering release. No model is trained or activated by these tools. Neither a funded-pilot date nor confidence in future profitability follows from passing a devnet rehearsal.
