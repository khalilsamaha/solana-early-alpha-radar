# Project roadmap — updated 19 October 2026

The consolidated direction is [EDGE-RESEARCH-PLAN.md](EDGE-RESEARCH-PLAN.md). [PROJECT-HISTORY.md](PROJECT-HISTORY.md) records prior development.

Goal: evaluate whether launch characteristics and timely evidence select realistically enterable and exitable opportunities. Faster momentum alerts alone have not demonstrated an edge. Keep current entry rules frozen while researching launch quality.

| Stage | Status | Next gate |
| --- | --- | --- |
| Hosting, notifications and scanner recovery | Established in supplied host tests | Backblaze retained as pay-as-you-go; recovery of previously failed cloud jobs is not yet verified |
| Paper, observation-quality and walletless quote evidence | Operating | Preserve failures, timing and versioned denominators |
| Pool/exit evidence and launch foundation | Deployed; initial host readiness, launch capture and quote backup verified | Monitor sustained coverage, retention and new backup failures |
| Launch-feature study | Six-hour post-update timing verified; paired feed/route audit built | Rule out local-only/cache-only explanations; define bounded prospective source validation before changing signals |
| Prospective strategy validation | No demonstrated edge yet | Cost, tail-loss, quote-failure, selection-bias and independent-period gates |
| Execution engineering | Host atomic devnet token lifecycle and recovery passed; offline signed position accounting built | Host accounting self-check, supported router validation and controlled multi-transaction integration |
| Funded pilot | Not ready | Evidence and controls plus explicit wallet/action/loss-budget approval |

The current quote budget provides at most 48 watches per cohort per day. Collection time depends on independent usable evidence; 1,000 scanner launches do not mean 1,000 executable samples. There is no justified real-money testing date.

Current paired evidence audit: [PAIRED-FEED-AUDIT.md](PAIRED-FEED-AUDIT.md). Current instrumentation and backup-cap investigation: [FEED-PROVENANCE.md](FEED-PROVENANCE.md). Current report update: [PRICE-RECONCILIATION.md](PRICE-RECONCILIATION.md); joined evidence: [LAUNCH-QUOTE-UPDATE.md](LAUNCH-QUOTE-UPDATE.md); original context study: [LAUNCH-STUDY.md](LAUNCH-STUDY.md). The launch foundation deployment is recorded in [LAUNCH-FOUNDATION-UPDATE.md](LAUNCH-FOUNDATION-UPDATE.md).

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
