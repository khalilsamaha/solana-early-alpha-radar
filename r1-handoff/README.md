# Offline handoff and rollback coordinator

This additive coordinator consumes the accepted exact-target stop proof and orders
endpoint binding, consumer readiness, one synthetic owner attempt, research
retirement, shared shutdown and explicit direct restoration. It does not implement
Docker/provider adapters or expose a production/offline host launcher yet.

Input must independently replay the complete four-record r1-control generation,
including its exact accepted source digest, network-none target and local stop.
Pending/lost-response control generations cannot enter handoff. The proof bytes
are retained inside the new immutable claim. All new receipts bind operation ID,
prior identities and exact source generation. Consumer image and restored image
must match the accepted candidate. Restoration must match the original config
identity and restart policy, and use a new actor identity. An uncertain shared
shutdown cannot reach restoration.

Each intent is fsynced before backend dispatch. A lost response leaves a pending
operation; there is no automatic retry, continuation, fallback or restore method.
A failed writer is poisoned. A stable private registry consumes one claim and
cannot be rearmed. Read-only recovery checks canonical hash chains, UTC chronology,
actor generation, source identities and unchanged bytes without calling a backend.
A copied registry does not acquire a new identity.

Research retirement preserves its outcome through shutdown and rollback. Clean
unsubscribe may preserve discovery in the offline model; upstream-aborted cleanup
must report discovery stopped. Completing rollback never turns failed cleanup into
successful research. Local closure never claims provider connection/billing proof.
Every outcome retains production_activation_authorized=false.

The backend interface is deliberately injection-only. Development tests use an
explicit state model with no processes, Docker, provider or remote operations.
They validate coordinator semantics and interruption boundaries, not native adapter
behavior or production handoff. A receipt is only as good as the later adapter's
observations; this module is not independent attestation. The network-none scope
cannot authorize a real provider session.

Do not request another Kali check for this coordinator alone. First connect the
image-bound native consumer/owner and exact-target transition adapters, including
owned cleanup and observation-backed restoration, then run one consolidated host
batch across normal, cleanup-failure and interrupted transitions. The original
r1-control and image gates remain accepted and are not rerun unchanged.
