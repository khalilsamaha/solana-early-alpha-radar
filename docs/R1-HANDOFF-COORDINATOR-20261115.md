# Remaining handoff sequence: coordinator implementation — 15 November 2026

After acceptance of exact-target stop, this additive increment implements the
remaining ordered handoff/rollback coordinator under r1-handoff. It consumes the
complete accepted control proof; incomplete or pending control evidence refuses
entry. It then orders endpoint binding, consumer readiness, a single synthetic
owner attempt, research retirement, shared shutdown and explicit restoration.

Each operation has durable intent before dispatch, an exact operation/generation-
bound receipt, and durable confirmation afterward. Consumer image, endpoint,
actor identities, restoration configuration/policy and predecessor are checked.
Uncertain operations consume the generation and refuse retries. Failed research
cleanup remains failed even after successful offline rollback. Recovery is
read-only and never dispatches a backend or resumes a generation.

Development acceptance: 20 coordinator tests, including all twelve before/after
fault positions across six actions, plus the 17 interacting control tests pass.
The failure matrix includes missing/foreign receipts, actor aliasing, stale image,
wrong restoration configuration, interrupted shutdown, torn/replaced journals,
fsync failure, clock regression, concurrent attempts and repeat dispatch.

IMPORTANT SCOPE: test backends are explicit in-memory state models. There is no
new Docker/provider adapter or host launcher in this increment. A passing modeled
transition is not native process, provider connection, retention or production
handoff evidence. The coordinator has no live authorization path; only the
accepted network-none control generation can enter. The currently accepted inert
control target is not silently converted into the real scanner's production
configuration. Real scanner binding requires a separately reviewed adapter/profile.

No new Kali command is requested for this coordinator alone. Next consolidate
native image-bound consumer/owner adapters, exact target observations, restoration
and owned cleanup against this contract, then provide one complete host batch.
Do not repeat the accepted image or local-stop batches unchanged.

This moves engineering within collector/handoff prerequisites. Production rollout,
live supervision/credentials, real variable-session preservation, retention/capacity
and approved measurement/exposure terms remain open. November 19 is unconfirmed;
no source pilot or 21-day study clock has started. Five-working-day engineering cap
unchanged, remaining allowance unknown; no extension inferred. November 20 E0
held-state checkpoint and December 31 scope/verdict checkpoint remain unchanged.
