# Restricted swap rehearsal — 19 October 2026

The latest host preflight passed exact replay: fifteen self-check cases and a six-request pool/program snapshot at slot 512909802. PR #34 CI passed. Wallet/fee checks remained untested by that pool-only capture.

This release adds a separate constrained signer, immutable one-attempt files, fresh preflight integration and signed simulation accounting. Synthetic tests use disposable unfunded keys and mocked RPC. They cover exact message binding, fixed caps, interruption, no repeated signing, stale evidence, stop markers, fee/native/token discrepancies and transport failures. Public reports withhold signed wire and private keys. There is no send method or production position-book connection.

The practical host action is an offline twelve-case exercise plus a five-request public inventory of the dedicated devnet wallet for the reviewed pool's mints. This establishes whether test token accounts/balances exist before attempting real-wallet signing. No account creation, funding, token purchase, scanner restart or backup operation is requested.

See [scope, limits, commands and remaining gates](../swap-rehearsal/README.md). Next: use the inventory to choose an isolated devnet token setup, produce a fresh narrowly bound packet, verify signed simulation on the host, then connect one-send submission and exact receipt/position accounting. Financial readiness remains separate from execution engineering.
