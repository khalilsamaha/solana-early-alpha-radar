# Solana Early Alpha Radar

Research system for discovering Solana tokens, recording paper signals and observing walletless route quotes. The scanner and quote observer do not trade. Separate, explicitly invoked tools can sign and submit tightly scoped **devnet** test transactions; they are not connected to trading signals or mainnet.

**Latest integration consolidation: PR #68, 1 November 2026.** Fresh exit
balances, durable scoped closure and the unified lifecycle view passed their
host checks and all nine CI groups. A follow-up correction in PR #69 preserves
historical closure after a durable STOP and merged after all nine CI groups passed;
its strengthened 24-case host exercise passed on November 2. See the
[November 1 consolidation record](docs/EXIT-LIFECYCLE-CONSOLIDATION-20261101.md).
The [independent exit key backend](docs/RESTRICTED-EXIT-SIGNER.md) is locally tested;
its 27-case disposable-key host check passed. The next
[one-send exit transport](docs/EXIT-SUBMISSION.md) passed its 24-case synthetic
host gate. [Exit receipt accounting](docs/EXIT-ACCOUNTING.md) passed all 15 host cases.
The [fresh exit balance collector](docs/EXIT-BALANCE.md) passed all 18 host cases.
[Durable scoped closure](docs/EXIT-CLOSURE.md) passed all 21 host cases.
The [unified lifecycle view](docs/ADMISSION-LIFECYCLE.md) passed all 24 host cases.
This three-increment batch merged in PR #68 after all nine CI groups passed; see the
[November 1 record](docs/EXIT-LIFECYCLE-CONSOLIDATION-20261101.md).
No scanner deployment or live execution CLI is included. The next
[entry admission timing observation](docs/ADMISSION-TIMING.md) measures one
unsigned collection and raw validation without creating a reservation. Its November 2
host observation passed with only 74 ms remaining. The next
[exact signature replay optimization](docs/ADMISSION-SIGNATURE-REPLAY.md) reduces
repeated verification work while retaining every source read and original expiry.
Its host exercise passed all 30 cases; live headroom rose to 1,131 ms. The next
[isolated durable admission rehearsal](docs/DURABLE-ADMISSION-REHEARSAL.md) tests
an atomic local reservation commit and read-only recovery, without occupying the
operational slot or enabling signing.

**Current project review: 7 November 2026.** See the [current evidence, priorities and remaining gates](docs/PROJECT-REVIEW-20261107.md). PR #78 is consolidated; subsequent successor work is a separate feature increment. The independent successor backend passed 50 Kali checks; the next [connected signing rehearsal](docs/SUCCESSOR-SIGNING-REHEARSAL-20261107.md) measures the original deadline across collection, persistence and the separate key process. The corrected complete Kali signing rehearsal passed all 24 checks at 22:06:51 UTC with 1,106 ms of original-deadline headroom, including recovery and preserved holds. The [successor submission boundary](docs/SUCCESSOR-SUBMISSION-20261107.md) passed all 17 Kali checks at 22:31:31 UTC. The next [combined successor execution rehearsal](docs/SUCCESSOR-EXECUTION-20261107.md) measures collection, signing, preflight, one send and lost-response recovery under the original deadline. Its CLI remains offline only; real network timing and exact receipt reconciliation remain separate gates. The paragraphs below retain release provenance.

**November 8 current host result:** the pinned-snapshot correction passed 27
preliminary checks but the connected Kali operation returned 216 ms late after
one synthetic send. Recovery and preservation assertions were not reached.
The [offline phase-cost diagnostic](docs/SUCCESSOR-PROFILE-20261108.md) measures
remaining validation, signer, transaction and submission costs without changing
execution rules. Complete Kali timing acceptance remains blocked; no operational
submission or funded pilot is approved.


**October 25 engineering release.** The [consolidated release and rollback procedure](docs/ENGINEERING-RELEASE-20261025.md) brings the frozen-study tools, controlled devnet spending/recovery, two-cycle accounting and local readiness inspection onto one source base. The release does not deploy the scanner or enable mainnet trading. The **October 28 frozen review is complete: no strategy or model is promoted**. See the [review decision and offline diagnostic](docs/FROZEN-REVIEW-DECISION-20261028.md). Engineering reliability can improve independently; profitable execution remains unproven. The [October 29 availability confirmation](availability-study/README.md) adds a separate fixed-window research protocol after the accepted diagnostic replay.

**October 27 observation batch, under PR review:** the [consolidation record](docs/OBSERVATION-CONSOLIDATION-20261027.md) joins fresh quotes, locked reservations, unsigned simulation and single-leg cost evidence. Host checkpoints passed; round-trip economics and execution approval remain separate gates. No scanner deployment is required.

This repository imports the deployed source captured on **2026-10-09 at 21:59 UTC**. The original hashes are preserved in SOURCE-REVIEW-MANIFEST.json. Subsequent changes are reviewed separately; see docs/FAST30-UPDATE.md for the deployed follow-up and sampling update, and docs/EVIDENCE-UPDATE.md for the subsequent evidence diagnostics update.

| Directory | Component |
| --- | --- |
| `scanner/` | Scanner 0.2.9, dashboard and SQLite evidence store; includes memory, worker and research-quality patches |
| `quote-observer/` | Walletless quote observer 0.9.0 in source, separate evidence ledger; confirm deployed version with host inventory |
| `research-tools/` | Research collector and scenario analysis 1.1.0 |
| `quality-tools/` | Fast30 timing, coverage, joined price/quote reports and registered shadow comparisons |
| `forward-study/` | Fixed feature/target protocol, fitting guards, immutable model freeze and later unseen evaluation |
| `devnet-pool/` | Controlled test-token pool, signed entry/reverse, exact receipts and read-only recovery |
| `position-book/` | Generic offline budget/position tests plus separate historical controlled-receipt accounting |
| `docs/` | Current roadmap, import provenance and development workflow |

The complete project record is in [project history](docs/PROJECT-HISTORY.md). The research concept is in [edge research plan](docs/EDGE-RESEARCH-PLAN.md); its dated phase descriptions are historical. The [current project review](docs/PROJECT-REVIEW-20261022.md) distinguishes implemented tools, supplied host evidence and remaining gates.

Controlled receipt accounting is available for [one historical cycle](docs/CONTROLLED-POSITION-UPDATE.md) and [the fixed two-cycle rehearsal](docs/TWO-CYCLE-ACCOUNTING.md). The latter complements prospective spending reservations; historical imports never retroactively grant pretrade approval.

Start with [development instructions](docs/DEVELOPMENT.md), [current roadmap](docs/ROADMAP.md) and [import review](docs/IMPORT-REVIEW.md). Component READMEs are preserved historical documentation; they may describe earlier deployment layouts.

The [local devnet readiness check](docs/DEVNET-READINESS.md) consolidates the fixed two-cycle journals, spending state and historical accounting into one read-only report. A consistent result does not authorize another cycle or assess the frozen strategy study.

The [private evidence snapshot and isolated restore check](docs/PRIVATE-EVIDENCE-BACKUP.md) preserves closed devnet journals and accounting locally, excludes the signing key, and verifies a disposable stopped copy. It does not restore into the active wallet or provide off-machine disaster recovery.

The [consolidated operational review](docs/OPERATIONAL-REVIEW.md) checks local health, release files, backup stages and preserved capture windows without evaluating the frozen study. A separate explicit capture-only helper bridges evidence before the October 28 review.

The [fresh controlled quote observation](docs/FRESH-CONTROLLED-QUOTE.md) derives an
integer quote from current raw pool evidence, builds an unsigned instruction and
rechecks the pinned deployment, account balances and scoped local reservations.
It makes at most 18 public devnet reads when explicitly invoked. It cannot sign,
submit, reopen a completed cycle or activate a research model.

The separate [unsigned quote simulation](docs/UNSIGNED-QUOTE-SIMULATION.md) adds
one explicitly requested devnet simulation and checks its own token/native
pre/post balances against a new quote. It cannot sign or send a transaction.

The [locked admission and signed acknowledgment checkpoint](docs/LOCKED-ADMISSION-BINDING.md)
connects raw evidence to a separate durable reservation under the controlled wallet
lock, then verifies an existing signature against the exact reserved message.
The [durable handoff](docs/DURABLE-SIGNER-HANDOFF.md) adds one-call adapter dispatch
and a same-ledger accounting outbox; its host check passed and PR #63 consolidated
the batch. The next [receipt gate](docs/ADMISSION-RECEIPT-GATE.md) binds raw receipts
to that handoff and replays entry effects in the same ledger while retaining all
commitments. Its host check passed. The [restricted signer backend](docs/RESTRICTED-ADMISSION-SIGNER.md)
now independently reconstructs the message and saves a one-shot acknowledgment.
Its 19-case disposable-key host check passed. The next
[admission submission and receipt gate](docs/ADMISSION-SUBMISSION-GATE.md) adds an
internal one-attempt devnet transport and bounded receipt collection. Its synthetic
host check passed all 18 cases; PR #64 consolidated this batch with passing CI.
There is no service or execution CLI wiring; allocations
remain reserved and no new cycle is approved.

The next [collected entry accounting](docs/ADMISSION-ENTRY-ACCOUNTING.md) increment
records acquired token deltas and paid versus retained fees in the same admission
ledger. Its 15-case host check passed. The next [combined private recovery
check](docs/ADMISSION-RECOVERY.md) includes the admission sibling and original
historical journals, replays them in a stopped temporary copy and preserves unknown
commitments. Its 19-test host check passed. Delayed exit integration and release
remain gated.

The [fresh delayed exit preparation](docs/ADMISSION-EXIT-PREPARATION.md) binds
new raw evidence to the acquired entry quantity and remaining fee commitments in
the same ledger. Its 27-case host check passed; live exit collection/signing and
submission remain unconnected. No production restart is needed.

## Checks

Requires Node.js 24.10 or newer in the 24.x series and Python 3.12. There are no third-party runtime packages to install for these tests.

```bash
bash scripts/check.sh
```

GitHub Actions runs the same offline tests on pushes and pull requests, plus source hygiene and original-package integrity checks. No production credentials are needed. CI does not deploy, send notifications, call market providers or trade.

## Deployment boundary

Kali remains the running host. **Do not run Docker Compose from this new layout against production yet.** Moving Compose into `scanner/` can change its project name and select a different database volume. A separate deployment migration must preserve the existing Compose project, environment and named volume, with verified rollback.

Paper price changes and route quotes are research observations, not fills or demonstrated profitability. Fast30 is a shadow cohort: no additional notifications or trade execution; bounded follow-up priority is recorded separately.

The [admission-owned exit collector](docs/ADMISSION-EXIT-COLLECTOR.md) binds fresh
raw devnet evidence to acquired inventory and held fees. Its portable check is
offline; atomic persistence and exit signing remain separate gates.

The [atomic collected exit preparation](docs/COLLECTED-EXIT-PREPARATION.md) stores
fresh raw evidence and collection provenance together in the admission ledger,
with independent replay and rollback checks. The host exercise is offline only;
restricted exit signing and submission remain unconnected.

The [durable exit signing handoff](docs/EXIT-SIGNING-HANDOFF.md) records the exact
request before one injected adapter call, validates recovered signatures, and
preserves uncertainty across interruptions. Its 21-case host check passed. The
[independent exit key backend](docs/RESTRICTED-EXIT-SIGNER.md) now connects through
an internal explicit opt-in, with no live execution CLI. Its host exercise uses
disposable keys. The [exit transport increment](docs/EXIT-SUBMISSION.md) adds an
internal one-attempt path and keyless recovery, with an offline-only host CLI.
Final receipts and allocation reconciliation remain separate gates.

The [fresh collection-to-signing integration](docs/FRESH-SIGNING-INTEGRATION.md)
connects bounded raw collection to the durable signer handoff internally. Its
17-case CLI is synthetic-only; live sender integration and latency acceptance
remain open. The isolated unsigned commit/recovery host gate passed November 2.

Current timing follow-up: the latest Kali report is recorded in
[the combined rehearsal record](docs/SUCCESSOR-EXECUTION-20261107.md#third-november-8-host-result).
The [phase-cost diagnostic](docs/SUCCESSOR-PROFILE-20261108.md) is diagnostic only;
it does not replace the unchanged 34-check acceptance command.
