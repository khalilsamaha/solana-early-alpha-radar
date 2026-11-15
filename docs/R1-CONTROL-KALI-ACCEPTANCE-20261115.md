# Exact-target service control: Kali acceptance — 15 November 2026

Accept published 3e168f8b8017b182251d82b45d33b23448751cc4, tree
078c4f7a76da59ce94bebe6cf1f310768488e353, for the isolated service-control scope.
Uploaded acceptance(6).zip SHA-256:
51792f6850124eca682f33639765a1b78e7df5d731d8367cc69d5700326a1459.

All eight source hashes match. The log records 17 tests, zero errors/failures/skips
and no detected runtime diagnostics. Independently replayed all three complete
claim/journal pairs and matched their recovery objects exactly, including source
digest, container/label identity, readiness, deliberate fault and cleanup receipts.

| Case | Journal records | Durable state | Pending action |
| --- | ---: | --- | --- |
| normal | 4 | locally-stopped | none |
| lost-update | 1 | prepared | disable_restart |
| lost-stop | 3 | restart-disabled | stop |

All three distinct disposable containers report readiness, removal and reaped
clients. Both lost-response fault markers were reached. Their pending state is
retained despite disposal: fixture cleanup is not retroactive confirmation.
All recovery results deny automatic resume, shared startup, provider-connection
closure and billing-cutoff claims. Normal establishes local Docker stop only.

Reported run: November 15, 08:47:18.027330–08:47:23.820531 UTC /
09:47:18–09:47:23 CET. This is supplied artifact review, not live Kali/Docker,
provider/RPC or current-balance observation. No unchanged repeat batch is needed.
The image acceptance and all E0 holds remain unchanged.
