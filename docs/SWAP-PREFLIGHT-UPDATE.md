# Combined devnet preflight release — 19 October 2026

The supplied fourteen-case program self-check and five-request actual ProgramData capture replayed exactly. The observed deployment at slot 512857731 is now pinned as an observation baseline, with its upgrade authority and lack of source/build verification explicit.

This release combines program and pool evidence in one finalized account batch, rejects deployment drift and stale account observations, and optionally checks a current original unsigned packet against wallet balances, blockhash validity and exact-message RPC fee. It never refreshes a packet or authorizes a signature. Offline replay preserves original observation time.

The host gate is fifteen offline cases followed by a six-request read-only capture of the previously reviewed devnet pool. Packet-mode wallet/fee checks are covered by synthetic tests but remain an actual integration gate. No scanner deployment, strategy, quote admission, model, notification, funding or Backblaze change is included.

See [commands, evidence boundaries and next integration](../swap-preflight/README.md). Development must next connect restricted devnet signing/simulation and durable receipt accounting before considering a controlled swap rehearsal. Engineering progress is not evidence of profitable trading.
