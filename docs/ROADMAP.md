# Project roadmap — updated 31 October 2026

Latest checkpoint: [PR #67](https://github.com/khalilsamaha/solana-early-alpha-radar/pull/67)
consolidated host-accepted restricted exit signing, one-send transport and receipt
accounting. All nine CI groups passed at the final reviewed head.
Merged source: `46cb51cd457a39def47248fe01883edf67d184eb`.
See the [consolidation record](EXIT-EXECUTION-CONSOLIDATION-20261031.md).

The [independent restricted exit key backend](RESTRICTED-EXIT-SIGNER.md) is built
and locally tested, including full-source signing, keyless acknowledgment recovery
and isolated restore. Its 27-case disposable-key Kali exercise passed at
18:14:04 UTC on October 31. [One-send exit transport and recovery](EXIT-SUBMISSION.md)
passed its 24-case synthetic host check at 18:37:40 UTC on October 31.
[Collected exit receipt accounting](EXIT-ACCOUNTING.md) passed all 15 host cases at
18:59:57 UTC on October 31. The next [fresh exit balance collector](EXIT-BALANCE.md)
is built with an 18-case offline host exercise pending. Durable scoped closure,
allocation release and live timing acceptance remain open.
The dated sections below preserve prior milestones.

Current task/subtask status is in the [progress overview](PROJECT-PROGRESS-20261030.md).
PRs #60–#64 consolidated the accepted post-entry, fee, atomic rehearsal, admission
and transport increments. The live atomic simulation passed its October 30 host
gate. Separate delayed transactions remain an open integration task.

The [October 25 consolidation](ENGINEERING-RELEASE-20261025.md),
[October 27 observation batch](OBSERVATION-CONSOLIDATION-20261027.md) and
[October 29 consolidation](ENGINEERING-CONSOLIDATION-20261029.md) preserve earlier
engineering milestones. The [October 22 review](PROJECT-REVIEW-20261022.md) explains
the strategy assessment, and [PROJECT-HISTORY.md](PROJECT-HISTORY.md) preserves the
earlier project record.

Goal: establish whether entry-time evidence identifies realistically enterable and exitable opportunities. More alerts and faster detection alone have not established a profitable strategy.

| Workstream | Current scope | Next gate |
| --- | --- | --- |
| Hosting and backups | Existing Kali services and backup tooling; no deployment change in this release | Current host health and backup success need their own operational evidence |
| Scanner and walletless quotes | Existing discovery, paper signals, three-cohort sampling and explicit failures | Preserve timing, versioned denominators and retained evidence |
| Frozen comparison | October 28 review complete; four fitted groups reached evidence minimums, no model promoted | Confirmation registered October 29; observe October 30–November 5 UTC, review November 6 00:05 UTC |
| Controlled devnet execution | Fixed two-cycle identity, cumulative spending reservations, explicit one-send paths and bounded unsigned recovery | Keep the completed rehearsal closed; any further execution needs a separately scoped design |
| Accounting and readiness | Two-cycle receipt reconciliation, idempotent historical accounting and strictly read-only readiness; local key-excluded evidence snapshots with isolated restore checks | Host isolated restore accepted; encrypted off-machine recovery and key custody remain separate work |
| Execution economics | Host-accepted controlled quote, exact unsigned simulation, scoped local reservations and single-leg fee-cap funding | Same-simulation post-entry collector and exact reverse-message host checks accepted; exact reverse fee/conditional caps host accepted; ordered atomic draft and live combined simulation accepted; admission-owned exit signing/submission and final allocation reconciliation remain pending |
| Funded pilot | Not enabled | Separate strategy review, mainnet-specific validation, execution-cost evidence and explicit pilot scope/limits |

The completed frozen review used 781 forward watches. Four fitted groups met the original 200-label and seven-UTC-date minimums; two availability models remain unfitted. Meeting those minimums did not establish an economic edge. Richer context models did not improve the profit prediction, while the simpler early-activity exit-availability model offers a specific failure-filter hypothesis. See the [decision and limitations](FROZEN-REVIEW-DECISION-20261028.md).

Immediate sequence:

1. The October 29 diagnostic replay passed. The original report/model identities and all forward group counts and fixed-threshold partitions agree. Partial training captures remain explicitly unavailable for full training-distribution comparison.
2. Registered October 29: the [separate availability confirmation](../availability-study/README.md): unchanged early-activity legacy weights and threshold, seven full future UTC days, development-token exclusions, fixed review time and separate availability/economic reporting. Production sampling and alerts stay unchanged.
3. Preserve bounded captures every 48 hours and at the final review. No automatic timer is added in this increment. The completed October study is development evidence; do not extend or reinterpret it as a fresh holdout. Study registration prints the authoritative dates.
4. The [reverse observation](REVERSE-COST-OBSERVATION.md) passed on October 29. The [independent paired cost scenario](PAIRED-COST-OBSERVATION.md) also passed on the host. The [offline post-entry contract](SIMULATED-POST-ENTRY-PROJECTION.md) now validates the declared same-response pool transition and projects the reverse amount. The [bounded live collector](POST-ENTRY-COLLECTOR.md) passed its host check. The [projected exit-message validator](PROJECTED-EXIT-MESSAGE.md) passed its October 30 host observation. The [exact-message fee and conditional cap check](PROJECTED-EXIT-FEE.md) passed after the duplicate-validation correction, with 582 ms of freshness headroom. The [ordered atomic draft and transfer-trace contract](ATOMIC-REHEARSAL-CONTRACT.md) is the next development increment, not a live simulation pass. Complete round-trip funding and sequential exit execution remain unverified. The existing controlled devnet cycles remain closed. Mainnet validation and a separately agreed mechanics pilot still have their own gates.

No calendar date or expected revenue is justified for a real-money pilot. Deployment layout migration, private journal disaster recovery, general portfolio management and arbitrary mainnet routes are not completed by this source consolidation.

## Next execution integration sequence

1. **Implemented, not deployed:** exact-message network-fee observations and native
   account evidence feed the standalone cost model. Both message/quote identities
   are retained, but their association is not a verified swap. Missing evidence
   remains unavailable; devnet has no USDC-economic interpretation. See
   [integration release](EXECUTION-COST-EVIDENCE-UPDATE.md).
2. **Development increment, host synthetic check accepted October 27:** a declared direct devnet quote
   now binds to raw unsigned instruction/account evidence, exact amounts and
   minimum output, and balances after declared reservations. This uses the
   existing controlled route to test the integration contract; it does not
   complete or replace mainnet validation. See [scope and host check](QUOTE-STATE-BINDING-UPDATE.md).
   **Remaining engineering gate:** one narrowly supported mainnet route/message
   validator, with input/output mint and amount/minimum-output checks, fee/tip
   treatment, account creation/rent, token-account ownership and principal
   spendability. Unsupported routes and extensions remain blocked. Build and test
   read-only/simulation integration before connecting a signer.
3. **Local reservation read integrated, host inspection accepted October 27:** the controlled
   two-cycle ledger can now supply scoped token/native commitments directly to
   the devnet quote/account reviewer under the wallet lock. Public reservation
   summaries are not accepted as its authority. This is an observation, not a new
   atomic reservation or wallet-wide budget. See [integration and host command](LOCAL-RESERVATION-INTEGRATION.md).
   **Fresh quote observation implemented, host live check accepted October 27:** the standalone
   reader calculates a direct-pool exact-input quote, uses it in a fresh unsigned
   instruction and rechecks raw account/program evidence and current local
   commitments. It refuses changed economic pool inputs and stale original clocks.
   See [bounded host command and limitations](FRESH-CONTROLLED-QUOTE.md).
   **Unsigned simulation and single-leg costs accepted October 27:** the standalone
   [simulation command](UNSIGNED-QUOTE-SIMULATION.md) compares its own token/native
   effects with a newly calculated quote, rechecks returned config/deployment bytes
   and rereads local reservations without signing or sending. A deployment change
   first stopped the run. Raw program evidence was reviewed, and a new fixed pin
   is selectable only for unsigned simulation. The 18:46 and 18:58 UTC host
   checkpoints passed; the original sender pin remains unchanged.
   [Cost readiness](CONTROLLED-COST-READINESS.md) funds the full message fee cap
   from final locked reservations; exit costs and round-trip economics stay unknown.
   **Next engineering gate:** finish consolidated regression/PR review, then build
   fresh exit-leg evidence and explicit round-trip funding/cost assessment. Later
   execution integration must bind a validated route to durable intent and
   authoritative reservations, recheck before the send boundary, and exercise
   stale evidence, insufficient balance, STOP, unknown outcomes and idempotent
   recovery. None of this reopens the completed rehearsals.
4. **Independent research gate:** the October 28 review did not justify promotion.
   Replay the preserved evidence, then audit the specific availability hypothesis.
   Revised models or filters require a new prospective comparison; retain all original results.
5. **Funded test gate:** only after route, simulation, accounting, operational and
   strategy reviews, agree a separate disposable test budget and hard exposure
   limits. A small execution-mechanics test would establish actual fee/fill behavior,
   not expected profitability. Positive execution readiness cannot substitute for
   evidence that the strategy works.

This sequence separates two questions: can the system execute and reconcile the
intended trade reliably, and do its signals identify an economic edge? Both need
evidence. The current release advances the first without changing the second.

## 15 October 2026 update

The first offline ML benchmark is complete but does not demonstrate an edge. Next: consistent supplemental entry context, a frozen forward benchmark and a dry-run execution/reconciliation harness. See [entry context deployment](ENTRY-CONTEXT-UPDATE.md) and [real-money gates](REAL-MONEY-GATES-20261015.md). No live trading or ML activation.

## 16 October 2026 update

Consistent entry context was verified on all 802 new signals in the supplied post-update window. Twenty-five quote watches still show poor results and two watches with repeated provider-reported reverse-quote failures; capture success is not a strategy pass. Added per-field metadata provenance, a failure-aware offline exit-availability review and idempotent observer installation. See [deployment and validation](METADATA-PROVENANCE-UPDATE.md). Next: validate new provenance, freeze the richer-feature comparison protocol, and develop a dry-run execution/reconciliation harness. No funded pilot or model activation is approved by these results.

## 16 October 2026 — fixed comparison and execution simulation

Metadata provenance passed its first host evidence check. The richer-feature protocol, data audit, model freeze and later evaluator are now implemented; fitting remains conditional on per-target/cohort counts and later unseen evaluation. A simulation-only persistent execution/reconciliation harness is implemented and tested. Live chain integration, signing and independent live stop controls remain unimplemented. See [release notes](FORWARD-AND-SIMULATION-UPDATE.md). No profit claim or funded-test date follows from this engineering milestone.

## 17 October 2026 — readiness details and public chain evidence

Reviewed 166 compatible watches across two UTC days. All three cohorts still fail the fixed fitting guards and have negative mean returned 30-second quoted changes. Added richer failure-aware readiness reports, a bounded public RPC evidence reader with offline tests, and source/container deployment inventory. The scanner and observer remain unchanged. See [commands, evidence and remaining gates](READINESS-RECONCILIATION-UPDATE.md). No model is trained or activated; the reader does not sign, submit or reconcile into a trading ledger.

## 17 October 2026 — offline transaction-intent comparison

Host inventory and readiness replay for the prior release passed. Added a separate offline lab binding declared transaction messages to wallet/token/native-balance expectations, with narrow standard SPL creation/closure checks and fee-only failed receipts. No signer or execution integration exists. Next: independently verified transaction identity, durable prior intents and recorded/devnet validation, while collecting the unchanged research protocol. See [release notes](INTENT-RECONCILIATION-UPDATE.md).

## 17 October 2026 — signed identity and durable intent journal

The prior six-case host self-check passed. Added strict legacy/v0 wire decoding, all-required-signature Ed25519 verification and a private SQLite intent journal with atomic registration, duplicate protection, a one-time unresolved submission boundary, restart recovery and sticky quarantine. No sender or signer exists; the eleven-case host self-check is pending. ALT-bearing messages remain unsupported until independent lookup resolution is implemented. Next: recorded-chain identity validation and separately scoped devnet tests, while the unchanged research protocol continues. See [release commands and scope](SIGNED-INTENT-JOURNAL-UPDATE.md).

## 17 October 2026 — signed journal host verified; recorded chain identity

The eleven-case host self-check passed with exact local replay. A newly captured existing public devnet transaction now verifies cryptographically against raw bytes and matches RPC JSON, with before/after cluster identity checks. Its ALT references are signed, but resolved addresses remain explicitly unverified. Added bounded single-transaction capture, replayable public evidence and adversarial cross-encoding/transport tests. No own transaction was submitted. Next: lookup-state resolution/provenance before integrating an independently controlled devnet execution workflow. See [recorded-chain release](RECORDED-CHAIN-UPDATE.md).

## 18 October 2026 — lookup consistency and outage recovery

The Kali recorded-chain capture passed exact offline replay, including two signed lookup descriptors. A separate bounded lookup-account audit now checks account bytes, owners, indices and address ordering while keeping historical state and execution approval unproven. Journal ALT admission remains blocked. The user reported approximately three hours of reboot downtime; a read-only recovery capture checks services, polling and timers. Exact outage bounds and recovery are pending host evidence. Next: review these reports and build a controlled simple devnet intent workflow alongside unchanged forward collection. See [lookup release](LOOKUP-EVIDENCE-UPDATE.md).

## 18 October 2026 — dedicated devnet preparation

Current lookup consistency passed host replay for 14 addresses in two tables. Recovery capture shows services available, while reported reboot timing conflicts with recorded boot/process times and remains unresolved. Added a standalone dedicated devnet wallet initializer, restricted self-transfer signer, durable prior intent and optional signed simulation. There is no broadcaster. First host gate: offline self-check and public wallet report; then explicit devnet simulation. Next: controlled devnet submission/finality/unknown-outcome recovery, token lifecycle and independent stop controls. Strategy fitting and real-money gates remain independent and unmet in the latest reviewed audit. See [release notes](DEVNET-REHEARSAL-UPDATE.md).

## 18 October 2026 — live simulation passed; controlled submission built

The dedicated wallet's live devnet simulation passed with 5,000 simulated lamports of fee and no submission. Added explicit one-send devnet execution, preserved expired-plan replacement (at most one), durable unknown-before-transport state, bounded finality/receipt checks, separate read-only recovery and a persistent stop marker. Host submission remains pending. Next: review its actual receipt, then token lifecycle and independent spend/position controls. Strategy and funded-pilot gates are unchanged. See [submission release](DEVNET-SUBMISSION-UPDATE.md).

## 18 October 2026 — finalized devnet recovery and signed token accounting

Host submission at 09:36 UTC reported a finalized one-lamport self-transfer, exactly one send request and a 5,000-lamport fee. Both public signatures/message hashes were independently replayed from the reports. Fresh-process recovery at 09:40 UTC preserved the same receipt and single boundary with zero network requests. This verifies local terminal recovery, not a second independent chain-finality observation or a forced power-loss test.

Added a standalone offline signed-token reconciler: full signed identity, standard SPL transfer-flow checks, creation/closure ordering, fee/rent separation, explicit failed/unknown outcomes, and a narrow existing-WSOL accounting path. Default intent-lab and durable-journal WSOL admission remain blocked. Next: host self-check, recorded/devnet token evidence, then supported wrap/unwrap and router-specific validation before any connection to an execution ledger. No signal, model, quote budget, mainnet execution or backup changes. See [release notes](TOKEN-RECONCILIATION-UPDATE.md).


## 18 October 2026 — host token checks passed; recorded flow capture built

The twelve-case signed-token host report replayed exactly. Added a separate read-only public token capture and replayable ordered flow check covering recorded counterparties, fees, supported funding/refunds and existing WSOL. Historical results explicitly do not establish prior intent. The development RPC attempt was unavailable; actual token capture remains pending on Kali. No additional day-long collection wait is needed for this gate. Next: inspect the selected transaction and address its supported lifecycle requirements before extending devnet execution. See [commands and boundaries](RECORDED-TOKEN-FLOWS-UPDATE.md).


## 18 October 2026 — actual recorded token evidence passed; controlled lifecycle built

The host eleven-case report and actual devnet token capture replayed exactly. The recorded transaction was a simple transfer between existing accounts, so creation and closure were not proven. Added a standalone fixed atomic WSOL lifecycle using the dedicated devnet wallet: two new accounts, a 1,000-lamport transfer and both closures, bounded by a narrow signer and separate durable one-send journal. Synthetic interruption and receipt tests cover the workflow; actual host execution is pending. Intermediate transient balances remain explicitly unobserved. No strategy, model, scanner or quote-admission changes. See [host commands and limits](DEVNET-TOKEN-LIFECYCLE-UPDATE.md).


## 19 October 2026 — host lifecycle/recovery passed; signed position accounting

The actual devnet lifecycle reported finalized success with one send and a 15,000-lamport fee. Independent signature/hash replay passed; fresh-process terminal recovery preserved the exact receipt with zero network requests or sends. Added a separate offline position book combining durable signed intents, raw token evidence, entry/exit continuity, principal/fee reservations, unknown-outcome recovery, persistent entry stop and contradiction quarantine. Synthetic host validation is next; no production sender enforces these limits yet. Supported router semantics and multi-transaction integration remain execution gates, while forward strategy validation remains independent. See [release details](POSITION-ACCOUNTING-UPDATE.md).


## 19 October 2026 — unsigned swap instruction contract

The supplied 04:31:10 UTC position report exactly reproduced all ten synthetic accounting checks with no network requests or transactions. Added a separate offline raw unsigned-message validator for one direct Raydium CPMM devnet exact-input contract: fixed account roles and permissions, atomic amounts/minimum output, allowed compute instructions, integer fee caps, message-bound caller fee assertion and short local deadlines. Twelve synthetic host cases and adversarial regression tests cover rejection paths. No signer is connected; chain/account/program state, policy provenance, RPC fee truth and simulation remain unverified. Next: host replay and a bounded independent state/preflight adapter before devnet swap integration. Strategy evidence collection continues unchanged. See [release scope and commands](SWAP-CONTRACT-UPDATE.md).


## 19 October 2026 — current pool/account state adapter

The 09:49:51 UTC host unsigned contract report matched all twelve expected cases exactly, with no requests or transactions. Added raw devnet pool/config/mint/vault/observation decoding, fixed authority and executable program-pointer checks, and a bounded read-only capture. Optional prior-packet mode binds wallet accounts, balances, exact-message RPC fee and blockhash validity to the original unsigned policy. The latest program transaction is only a one-result pool hint, not an authenticated prior intent; unsupported evidence is retained without resampling. Fifteen synthetic host cases and adversarial regression cover state and transport behavior. Development's single public devnet attempt stopped on its first request with network-error, so actual pool capture remains a host gate. No signer, sender, production integration or strategy change. See [release details](SWAP-STATE-UPDATE.md).


## 19 October 2026 — real pool state passed; deployment fingerprinting

The supplied 15-case pool-state self-check and actual devnet capture replayed exactly. The seven-request capture at 15:43:54 UTC observed consistent pool relationships at slot 512847269; both test mints retained mint authorities. Added standalone full ProgramData observations for the fixed devnet program: payload/header hashes, deployment slot, upgrade authority, and explicit baseline drift comparison from raw evidence. Five bounded read requests, no signer or transaction sender. Twenty-nine regression tests and a fourteen-case host self-check cover decoder, transport, replay and change detection. Actual ProgramData capture remains a host gate; fingerprints do not establish published-source equivalence or safety. Next: review the deployment observation and establish an independently reviewed baseline before connecting restricted devnet signing/simulation and durable accounting. Strategy collection and financial readiness gates remain unchanged. See [release commands](SWAP-PROGRAM-UPDATE.md).


## 19 October 2026 — deployment observation reviewed; combined preflight

The fourteen-case program self-check and actual five-request capture replayed exactly. Pinned that observed deployment at slot 512857731 without claiming source equivalence or safety. Added one combined finalized account batch for pool and program evidence, with optional wallet and exact-message checks. Separate account receipt timestamps prevent later requests from refreshing older observations; original packet deadlines and deployment drift remain blocking. Fifteen synthetic host cases and twenty-nine regression tests cover the integration. Actual combined capture is the next host gate; signing, simulation, submission and position-book integration remain disconnected. No scanner, strategy, quote budget, model or backup changes. See [release scope](SWAP-PREFLIGHT-UPDATE.md).


## 19 October 2026 — combined host preflight passed; restricted swap rehearsal

The 19:52:31 UTC host capture replayed exactly as `pinned-pool-snapshot` at slot 512909802, with six received public reads and unchanged observed deployment identity. All fifteen host self-checks matched and PR #34 CI passed. Added a separate exact-message devnet signer, durable one-attempt plan/signature storage, fresh preflight integration and signed simulation token/native accounting. Local tests use disposable unfunded keys and synthetic transport; no real-wallet swap signature or simulation is claimed. The next host action is a twelve-case offline exercise and public token-account inventory for the reviewed pool. Live packet production, devnet token provisioning if needed, one-send swap submission and position accounting remain integration work. No mainnet, strategy, model, quote-budget or backup change. See [release notes](SWAP-REHEARSAL-UPDATE.md).


## 20 October 2026 — controlled setup costs and fresh packets

The latest host rehearsal self-check and public inventory were replayed exactly. The dedicated wallet had 9,980,000 devnet lamports but no accounts holding either reference-pool token. Added live rent/config-fee estimation for a new controlled standard-SPL pair/pool, a production canonical swap packet builder, and immediate handoff into the existing restricted signed-simulation workflow. The builder preserves independent scope and minimum output and does not reset existing one-shot state. Token/pool provisioning and actual-wallet swap simulation remain pending. Strategy qualification and funded-pilot gates remain separate. See [release and host command](DEVNET-SETUP-UPDATE.md).


## 20 October 2026 — controlled token-pair provisioner

The setup-cost report passed exact replay: creation enabled, full setup estimate 185,980,040 devnet lamports, balance 9,980,000 and shortfall 176,000,040. The token-pair stage alone fits: 5,110,480 rent plus a fresh five-signature fee. Added an atomic two-mint/two-holder setup with fixed supplies, revoked mint authorities, absent freeze authorities, restricted signing, a 6,000,000-lamport rent-plus-fee cap, exact simulation, durable one-send boundary, receipt/account reconciliation and read-only recovery. Offline adverse-case tests use disposable wallets and synthetic RPC; actual host provisioning remains pending. Pool creation and swaps are separate next steps. See [release notes](DEVNET-TOKEN-PAIR-UPDATE.md).

## 20 October 2026 — test pair verified; controlled devnet pool

The actual token-pair report records one send and finalized success. Reconstructed intent/wallet signature and raw mint/holder accounts matched; 1,000 tokens per mint, no mint/freeze authority, 4,844,520 devnet lamports remaining. Added deterministic pool/vault/oracle/LP derivation, repeatable funding inspection, restricted signing, exact simulation, durable one-send initialization and read-only recovery. Deposits 500 tokens of each mint, retaining 500 for later swaps. Fresh deployment/config/account checks and strict receipt reconciliation remain required. Creation-fee caps are preflight checks, not on-chain ceilings. Actual pool execution is the next host gate; controlled swap and production position integration remain pending. Strategy qualification is unchanged. See [release notes](DEVNET-POOL-UPDATE.md).


## 21 October 2026 — finalized test pool and controlled swap simulation

The supplied 20 October 21:47 UTC report records one pool initialization send, finalized success, 500 tokens in each vault and 500 in each remaining holder. Independent public-evidence replay verified deterministic addresses, the reconstructed message and wire hashes, Ed25519 signature, raw post-account effects and exact 180,774,560-lamport debit. All 70 reported offline cases matched. Raw receipt verification remains a host-side check because that full receipt was not exported.

Added a fixed-scope adapter from verified local setup journals to the existing fresh packet, current account/program preflight, one-shot restricted signer and signed simulation. Explicit wallet/pool required; mint0 to mint1 only; 1,000 atomic input, minimum 990 output, zero priority fee and 10,000-lamport message-fee cap. No sender, production change or journal reset. Seventeen new tests exercise the real local signing path against synthetic transport and adverse interruptions. Corrected signature-count reporting after a durable signature with lost signer acknowledgement. Actual host swap simulation is the next gate; one-send swap execution, reverse-swap/position accounting and strategy qualification remain separate work. See [release instructions](CONTROLLED-SWAP-SIMULATION-UPDATE.md).

## 21 October 2026 — controlled signed swap simulation accepted; one-send execution built

The host's 04:35 UTC report passed the controlled simulation gate: 1,000 atomic input, 998 output, fee 5,000 devnet lamports, 21,405 compute units, one signature and zero sends. Public message/wire/signature and scope bindings replayed; raw account/simulation validation remains host-side.

Added a separate immutable `swap-execution-v1` lifecycle: fresh fixed-scope message, independent restricted signer, signed simulation, repeated current account/program checks, durable one-send boundary, bounded finalized receipt reconciliation and read-only recovery. Prior simulation bytes are preserved and its blockhash/signature state is checked before proceeding. Missing evidence stays unknown; contradictory effects quarantine; terminal status replays private receipt data. Actual host submission is now the next gate. Reverse-swap/round-trip accounting and strategy qualification remain separate subsequent work. See [release notes](CONTROLLED-SWAP-SUBMISSION-UPDATE.md).

## 21 October 2026 — receipt-bound reverse ready for host validation

The actual forward swap and zero-send terminal recovery passed review. The next release reverses exactly the acquired test-token quantity in its own one-send journal and reconciles both finalized receipts, original-token net change, residual acquired tokens and native fees. Current host scope is 998 atomic input/minimum 988; it is a fixed controlled test, not a market strategy rule. 27 new offline cases cover reverse signing/accounting and interrupted/failed paths. Next gate: actual reverse and recovery reports, then receipt-to-position/budget integration and operational stop/reconciliation exercises. Mainnet readiness and forward strategy evidence remain separate gates. See [host sequence](CONTROLLED-REVERSE-SWAP-UPDATE.md).


### October 27 deployment observation refresh

The full 18:38 UTC public program capture replayed exactly and corroborated the
18:30 deployment-drift diagnostic. A separate fixed observation is now selectable
only for unsigned simulation via `--deployment-observation-20261027`; the legacy
preflight/sender paths retain their prior pin. No source/build or behavior approval
is inferred from a matching fingerprint. Host unsigned simulation and single-leg
cost observations passed at 18:46 and 18:58 UTC respectively; report-level
verification limits remain explicit. Production collection and the
October 28, 17:30 Europe/Amsterdam frozen review remain unchanged.

### October 27 controlled cost integration

Host unsigned simulation on the explicitly refreshed deployment passed at 18:46
UTC (1,000 in, 998 calculated/simulated out, 5,000 lamport fee, 7.557 seconds).
Summary hashes/arithmetic/clocks were checked; uploaded raw RPC replay was not
available. `position-book/cost_cli.py` now recomputes single-leg funding and costs
from raw in-process evidence plus final locked reservations. The 18:58 UTC host
checkpoint passed: 13 offline cases, matching 998 output, 5,000 fee within 10,000
cap, unchanged closed journals and 7.337-second completion. The batch is now
under consolidated regression and PR review; see
[consolidation record](OBSERVATION-CONSOLIDATION-20261027.md). No round-trip
economics, sender activation, scanner deployment or frozen study change is implied. See [controlled cost readiness](CONTROLLED-COST-READINESS.md).


### October 30 — bounded live atomic simulation built

The 06:46 UTC host report reproduced all 18 ordered-message/trace contract cases.
A separate opt-in collector now prices and simulates the exact combined unsigned
message, normalizes only supported compiled/parsed transfers, reconciles raw
final token/native/pool/config/deployment effects and the Clock-bound oracle
reference update, then rechecks local reservations and the original deadline.
At most 23 devnet requests, no retries, signatures, sends or runtime changes.
Actual host success remains an acceptance gate. Atomic rehearsal does not satisfy
independent two-transaction exposure/funding or profitable strategy requirements.
See [scope and host sequence](ATOMIC-LIVE-REHEARSAL.md) and the
[current task roadmap](PROJECT-PROGRESS-20261030.md).


### October 30 — atomic host accepted; bounded exit commitments

The 08:27 UTC host observation met the original freshness window at 7.626 seconds
with 2.375 seconds remaining. Four transfers, zero acquired residual, exact 5,000
combined fee and final effect flags were consistent; all 21 portable cases matched.
Public arithmetic/hashes/clocks were reviewed; raw RPC replay remains host-side.
Added an opt-in v2 offline position policy with 1–3 explicitly budgeted exit attempts.
It reserves all caps before entry, counts durable registrations, keeps unknown
commitments, reconciles failed fees once and blocks exhausted capacity while
retaining open exposure. V1 ledgers/senders are unchanged. The 09:17 UTC host
report passed all 14 cases and matched the local result exactly. Next: batch
consolidation after CI, then a fresh raw-admission adapter. See
[scope and commands](BOUNDED-EXIT-BUDGET.md).


### October 30 — pre-sign admission prototype

PR #62 consolidated atomic rehearsal and bounded exit commitments after both CI
groups passed. The next development adds raw-evidence admission to a separate
private ledger: recomputed prices and simulation fees, all exit fee caps held,
exact message identities, a durable signing-unknown boundary and no automatic
release on expiry or process death. This prototype has no live reader/signer
handoff. See [scope, tests and host command](PRE-SIGN-ADMISSION.md).

### October 30 — handoff consolidated; receipt integration built

PR #63 merged the three host-accepted admission/handoff increments after both CI
groups passed. Main `c632bd7388faea410a5bc401e66e27fdff445807` matches the reviewed
tree. The next receipt gate validates exact raw signed evidence against the saved
handoff, stores terminal evidence atomically in the same ledger, and replays it
on reopening. Unknown/conflicting outcomes never release the original reservation.
Its synthetic host check is pending. Key-backend integration, actual submission
provenance, trusted RPC collection and authoritative allocation transitions remain
separate gates. See [receipt integration](ADMISSION-RECEIPT-GATE.md).


### October 30 — receipt gate accepted; restricted signer built

The 15:51 UTC host report matched all 14 receipt-gate cases. The next increment
connects the locked admission to an independent restricted devnet key process. It
reconstructs the message from the saved scope, checks the controlled pair/pool,
commits a one-shot attempt before signing, and supports existing-acknowledgment
recovery without key access. Only disposable keys and synthetic journals have been
used. The 19-case host check is pending; production wiring, one-send provenance,
trusted receipt collection and authoritative allocation transitions remain open.
See [signer gate and test scope](RESTRICTED-ADMISSION-SIGNER.md).


### October 30 — restricted signer accepted; submission/collection built

The 18:38 UTC signer host report matched all 19 cases and flags. The next internal
gate records an immutable send boundary in the existing admission database before
one fixed-devnet transport call. It checks genesis, blockhash and exact-message
fee under the original deadline, preserves unknown outcomes after interruption,
and never resends during recovery. A bounded genesis/base64 receipt collector
commits raw evidence before idempotent receipt application. All principal/fee
reservations stay held. The 18-case synthetic host check is pending; production
services and the frozen study are unchanged. Allocation ownership, sibling-ledger
recovery and delayed-exit integration remain open. See
[submission/receipt gate](ADMISSION-SUBMISSION-GATE.md).

The submission host report captured October 30 at 19:10:35 UTC matched all 18
cases and flags exactly. PR #64 merged the three-increment batch after local core
(1,354 Python and 345 Node tests), devnet-pool (266 tests), both CI groups and
code review passed. The merge does not deploy it.

## October 30: collected entry accounting increment

The [entry accounting gate](ADMISSION-ENTRY-ACCOUNTING.md) consumes the existing
genesis-bound receipt collection in the same admission database. It records only
the acquired token delta, excludes preexisting destination inventory, distinguishes
actual entry fees from retained commitments and is idempotent after interruption.
Failed entry fees do not release the principal; unknown receipts remain unknown.
Host acceptance is pending the 15-case synthetic check. Runtime, study protocols,
market polling and notification rules are unchanged. Next: complete private recovery
coverage, delayed exit lifecycle and final allocation reconciliation.

## October 31: collected preparation accepted; exit signing handoff built

The 17:39:33 UTC Kali report matched all 21 collected-preparation cases. The next
[exit signing handoff](EXIT-SIGNING-HANDOFF.md) adds a durable exact request before
one injected adapter call, signature/message verification, late acknowledgment
recovery, quarantine and semantic snapshot replay. Its 21-case host check passed at 17:55:29 UTC. No real key backend or sender is connected. Next: independent restricted
exit backend, one-send recovery, final exit accounting and residual allocation
release. Runtime and the November 6 confirmation study remain unchanged.
