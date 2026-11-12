# R1 source assessment — partial feasibility, funded activation blocked

Decision date: 2026-11-11. Evidence reviewed through development commit
`4d46229bdb8405eff55cc755fe1717f9be26152f`, with 181 Kali tests and the
uploaded real ordering bundle accepted. This closes the current bounded source
assessment with a **partial** verdict. It does not close the R1 engineering gate.

The three saved creation transactions demonstrate that the supported records
can be retrieved, decoded, checked for internal accounting consistency and
placed in provider-reported finalized block order. They cannot establish the
coverage, continuity or cost of a future paid trade feed. Do not extend this
assessment by automatically adding more small historical probes.

## What the evidence establishes

| Area | Evidence and limit | Decision |
| --- | --- | --- |
| Capture and local replay | Kali-accepted capture/controller; provider wire accepted on Kali with in-memory protocol peer | Offline process supervision accepted on Kali; local measurement accepted on Kali; complete-session handoff and independent replay accepted; no actual provider session/TLS test or live launcher accepted |
| Transaction identity/finality | Three original saved transactions pass the bounded public-RPC reconciliation | Provider-reported sample evidence; not independent consensus proof |
| Schema | Accepted event inspection and pinned schema comparison | Supports the observed layouts; not every program version, token or transaction type |
| Native-SOL accounting | Two observed creation-plus-buy transactions and one creation-only transaction pass their supported accounting paths | Internal sample consistency; not an executable counterfactual or profitable trade |
| Deployment window | Pump/Pump Fees modification slots predate all three samples, with stable current metadata | Temporal metadata only; not bytecode/source equivalence or historical configuration |
| Record positions | Cases 1,2,3 located at zero-based indices 22,45,89 in slots 468050019,468049941,468049828 | Sample block-list order established; no complete history or feed-order claim |
| Early trade coverage | Two selected creation transactions also contain a buy | Subscribing after observing creation cannot be assumed to include that buy; no omission rate measured |
| Recovery | No historical trade feed or complete gap-recovery path validated | Gaps must remain explicit; no silent continuation as complete data |
| Preservation | Handoff and synthetic B2 round trip accepted on Kali; downloaded bytes independently restored | One synthetic package only; real-capture coverage and retention remain open |
| Cost/connection coexistence | Documented paid feed and one-connection guidance; scanner already opens a separate connection | Numeric exposure approval and compliant connection design remain prerequisites |

The block result is sufficient to stop investigating **these three** positions.
Further sample success would not by itself close missing-event or recovery
questions. A study cannot treat a measurable subset as representative without
recording the selection denominator, missingness and exclusion rules.

## Collector and pilot decisions

Proceed with isolated implementation and offline validation. Do not activate a
paid subscriber, fund a wallet, alter the production scanner or start ML fitting.
The existing dedicated provider wallet can be reused; no replacement is requested.

The provider's [real-time documentation](https://pumpportal.fun/data-api/real-time/)
states one WebSocket connection at a time and distinguishes free creation/
migration events from paid token/account trades. The [FAQ](https://pumpportal.fun/FAQ/)
states live-only data and processed feed commitment. Both were rechecked on
2026-11-11. These statements do not resolve account/IP scope or establish a
hard billing cutoff. The baseline scanner code opens an unauthenticated data
socket and subscribes to creation/migration events; a second collector socket
must not be assumed compliant merely because it uses a funded API key.

On November 11 the owner supplied single-connection guidelines. One shared
authenticated connection is selected; the coexistence clarification request is
superseded. Before any live collector test, implement and validate shared ownership
and scanner integration, then review rollout. The supplied IP-enforcement detail
is not explicitly established by the reviewed official pages and is not treated
as an authenticated support reply. No provider message has been sent by this work.

A first pilot, if the remaining prerequisites pass, measures feed availability,
selection denominators, creation-to-subscription delay, finality matching,
unresolved records, explicit gaps and observed charges. It must not claim exact
curve reconstruction without historical state/configuration and executable
pricing applicability. No return labels or strategy tuning are authorized by
this measurement pilot. Outcomes must remain pass/fail/insufficient against a
registered measurement contract prepared before activation.

## Sequence to follow

1. **Completed for the synthetic package:** Kali-validated handoff and independent
   restore in the development environment. Original checksum receipt retained.
2. **Completed for the synthetic package:** B2 upload/download reported by Kali,
   downloaded bytes independently restored against the original checksum. Retain
   the remote object and receipt. Future live capture coverage remains to implement.
3. **Current — collector completion:** the provider wire is implemented with a
   pinned dependency and offline protocol tests, accepted on Kali at `a2fdf580`.
   Offline process supervision and local preservation are Kali-accepted at
   `1e8bed1a`. Local send/selection timing evidence is Kali-accepted at `ccf80858`.
   Complete capture/journal packaging is Kali-accepted at `324a32e4`, and the
   uploaded archive independently replayed. Its fixed-input B2 round trip is
   Kali-accepted at `58805ae6`, with independent replay of the downloaded complete
   session; see `R1-SESSION-BACKUP-20261111.md`. The selected connection design is in
   `R1-LIVE-READINESS-20261111.md`. The shared integration is accepted offline on Kali at
   `df6cbfa4`, including real Unix IPC; the normal archive independently replays.
   See `R1-SHARED-INTEGRATION-20261111.md`. Host process identity is accepted
   at `35b89c5e` with matching UID/namespace and no findings. The isolated Docker socket boundary
   is accepted at `747f44ed`, with all three disposable containers removed. Private credential delivery
   and the supervised shared-worker boundary are accepted on Kali at `bf2d9fcf`.
   The durable service lifecycle is accepted on Kali at `c0143106`. The combined isolated broker/scanner/Docker sequence is accepted on Kali at
   `a0003221`. The draft measurement evaluator is accepted on Kali at `268c03ad`, without
   approval of its terms or exposure. Interrupted evidence preservation is accepted on Kali at `f2db8ff9`. Next
   validate combined offline admission/handoff/finalization
   (`../r1-orchestration/README.md`), then finish production startup/rollback,
   live retention and registration/exposure controls before provider use.
   Prove bounded receive memory, cancellation/abort, credential redaction,
   no reconnect across gaps, and no paid subscription after a terminal limit.
4. **Pre-activation review:** combine Kali evidence, preservation receipt,
   connection decision and fixed measurement contract. Present exact funding and
   exposed-balance terms for owner approval. The earlier 0.05 SOL funding and
   0.02 SOL fee figures remain proposals, not approved spending.
5. **Conditional pilot:** up to 24–48 hours, stopping earlier at any cap. Review
   coverage/cost against the fixed contract. A satisfactory measurement pilot
   permits consideration of a separately registered study, not a profit claim.

These are engineering dependencies, not calendar promises. The agreed total
five-working-day build/validation effort cap remains in force; this document
does not restart it. If coexistence, recovery adequacy or the adapter cannot be
resolved within it, report the concrete blocked/insufficient verdict and
reassess scope. Do not extend data collection or retune on observed outcomes.

Full-gate Kali validation precedes PR/CI consolidation; merging still follows
the owner's decision. H1 closure, C1 inventory acceptance and independent E0
work are not changed by this R1 assessment. The confirmation-study timeline is
still conditional on adequate fresh data, registration and owner acceptance;
no new study start date is established here.
