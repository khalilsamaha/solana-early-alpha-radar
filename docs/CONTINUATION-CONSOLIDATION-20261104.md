# Continuation consolidation — November 4, 2026

This batch consolidates preserved live read-only observation, bounded exact
admission-history reuse, one explicit unsigned third-generation preparation,
independent signer validation, connected one-send/recovery rehearsal and safe
failure diagnostics. It follows consolidated main
`3ab01291461ced8a452300d1af80c0df1975ef34` (PR #75).

The November 4 diagnostic Kali report passed all 16 integration/fault cases and
14 independent Node signer cases at 19:13:19 UTC. SHA-256:
`9d411383143463911662dd29172873209d44bc3cd580073e4d1b49987f195117`.
The actual isolated signer used disposable keys and synthetic providers. Its
connected attempt took 5,550.364 ms and retained the original deadline. Twenty
collection plus five sender requests included one synthetic send whose response
was lost. Recovery observed that signature without resending, and repeat recovery
preserved the ledger byte-for-byte. Original/replacement/entry records and holds
were unchanged. Temporary fixtures were removed; no user wallet or real RPC was
used. The earlier review-required host run is retained in the engineering record;
its cause remains unknown, and this later pass does not establish latency stability.

Earlier host gates passed 24 preserved-observation cases, 12 history-reuse
integration and 10 independent signer cases, then 25 continuation-record and 14
independent signer-contract cases. Local mutation, deadline, STOP, corruption,
identity, storage, privacy, selector and source-preservation tests remain.
All CI partitions must pass on the exact PR head before merge. No tests or
execution deadlines are removed to obtain acceptance.

The third generation is a separate, explicit one-time continuation allowance,
linked to both immutable predecessors. The old replacement allowance is not
reset. Unknown signing/sending retains holds; no loop, automatic retry, fourth
preparation, entry allocation or mainnet execution is introduced.

The actual held devnet exit remains unresolved. The next increment is a narrowly
scoped operational boundary: read-only preflight, both exact predecessor hashes,
explicit signing/submission opt-ins, safe public output, and existing recovery
rather than re-execution. Its offline command tests precede any host execution.
Receipt reconciliation and scoped closure follow actual finalized evidence.
Scanner, quote sampling, notifications, frozen study and availability capture
policies remain unchanged. The November 5 and 6 captures remain separate.
