# R1 trade-data feasibility and proposed paid pilot

Date: 2026-11-11. Baseline: main merge
`c2da6dccdb23d81ef94501019fb868762d89db3f` (PR #83).

Status: the first offline capture-core increment is accepted on Kali after review
of the uploaded report; source adequacy remains unverified. See
`r1-data/README.md`. No live transport is implemented and no paid subscription,
wallet funding or study registration was performed by this work. The owner
reports the original project wallet is ready; reuse the dedicated PumpPortal
wallet rather than repeat setup. No numeric spending limit has yet been approved.

## Decision and boundary

Prioritize a capped R1 feasibility assessment before further C1 warning-screen
implementation. C1 inventory acceptance remains valid; trial readiness remains
blocked. H1 stays closed. Existing E0 work is independent. No ML fitting,
production scanner changes, trading endpoints, signing or executor development.

Question: can sufficiently complete, ordered and verifiable early trade data be
acquired within an acceptable budget to support a conditional curve simulation?
This pilot evaluates measurement quality and cost, not strategy profitability.

## Verified documentation and repository findings

Official pages checked on 2026-11-11:

- https://pumpportal.fun/data-api/real-time/
- https://pumpportal.fun/fees/
- https://pumpportal.fun/trading-api/setup/
- https://pumpportal.fun/FAQ/

The provider documents free new-token/migration streams, paid token/account
trades at 0.01 SOL per 10,000 events, and a linked wallet with at least 0.02 SOL
for token/account subscriptions. Its API key can authorize trades from the linked
wallet; it is not a read-only credential. Keys must remain on the owner's host,
outside source control, reports and chat. The collector must not need a private
key or expose trading operations.

The FAQ describes processed commitment and live data only; historical recovery
requires another source. The real-time page asks clients to use one connection.
The scope of that constraint across keys/hosts is not established here.

The baseline scanner adapter already opens an unauthenticated data connection
and subscribes to new-token and migration events. It does not collect trades.
Resolve compliant coexistence before connecting a separate pilot. Do not modify
or restart the production scanner merely to accommodate this experiment.

## Work sequence and stop conditions

1. Up to one engineering day for source/schema/billing feasibility. Establish
   event identity and ordering, creation/initial-reserve capture, fee/program
   identity, finality reconciliation and permitted gap recovery. Documentation
   alone does not prove these fields exist. Unknowns remain explicit.
2. Prepare an isolated collector and offline checks. Use deterministic bounded
   sampling, own receive clocks, raw bounded records, persistent session budgets,
   redacted errors, explicit reconnect gaps and a separate output directory.
   Prove stopping on time, message, disk and error limits and across restarts.
   Verify backup/restore/replay for the captured evidence.
3. Supply a pinned checkout and self-contained Kali test command only after the
   files exist. Kali offline acceptance precedes funded activation. Present the
   exact deposit, data-fee target and remaining billing uncertainties for approval.
4. Run a 24-48 hour pilot, stopping earlier on any cap. No rule outcomes are
   evaluated. Report sampling denominators, creation-to-subscription gaps,
   missing fields, finality/order coverage, reconstruction discrepancies,
   recovery limitations, observed charges and full-study cost projections.
5. Stop if reliable measurement or affordable coverage cannot be demonstrated.
   A successful pilot earns a separate study proposal, not a profitability pass.

Build plus validation retains a five-working-day effort cap. It is not a promise
of completion; blockers or exhaustion of the cap require a concrete reassessment.

## Proposed initial budget (not approved)

- Dedicated provider wallet; suggested total initial funding ceiling: 0.05 SOL.
- Intended pilot data-fee ceiling: 0.02 SOL (20,000 billed events at the published
  rate). Stop sooner if time/storage/quality limits are reached.
- No automated top-ups or extension. Deposit/withdrawal network charges must be
  disclosed separately before funding; no euro value is assumed.
- Message counting is an operational guard, not proof of a provider billing cap.
  Determine billing granularity, in-flight events and disconnect behavior before
  claiming a hard charge limit. If unresolved, all 0.05 SOL deposited must be
  treated as exposed; obtain the owner's acceptance before funding/activation.
- The 0.02 SOL access condition is not treated as a refundable deposit or an
  established required residual balance. Provider behavior remains to be checked.
- This sample may hit its event cap before 24 hours. It must stop anyway. The
  pilot gives a measured cost estimate, not a promise of all-mint coverage.

## Prerequisites for any subsequent confirmation study

Specify one primary rule/hold/realistic delay/cost scenario or a valid joint
testing procedure. Define feature cutoffs, initial-state and ordering guards,
impact limits, missing/migrated exit treatment, minimum coverage and uncertainty
requirements. Resolve the contradiction between unseen development outcomes and
estimating return variance from those outcomes. Set numeric comparator margins
and unresolved-path limits. Baseline requires its own absolute criterion.

Exact historical-state calculations are not exact executable counterfactuals:
inserted trades alter reserves and potentially later trades. State the assumed
future-flow model and limits on its validity. Neither simulated entries nor
per-entry returns prove feasible portfolio returns with finite capital.

Use fresh data after code/config registration and owner acceptance, at least
21 complete UTC days, a fixed endpoint, and pass/fail/insufficient outcomes.
Twenty-one days is a minimum, not a power guarantee. Any failure-only interim
look must be registered with the final test. No extension or retuning on outcomes.

A Nov 19 00:00 UTC start yields 14 complete days on Dec 3 and 21 on Dec 10.
Three to seven further days yields a Dec 13-17 report. These are conditional
examples, not scheduled commitments. December 31 remains the scope checkpoint.

## Delivery policy

Implementation may be published to a development branch under the existing
workflow. Full gate validation on Kali precedes PR/CI consolidation; merge still
requires the owner's explicit decision. The offline increment passed 44 synthetic
tests locally on Python 3.12.14 with ResourceWarning treated as an error. The
standalone runner also exercises capture, restart, a terminal message limit,
export, local restore and replay. This is not Kali acceptance, off-machine
preservation, feed-quality acceptance, deployment or full R1 gate closure.

## Kali acceptance — offline core only, November 11

Reviewed source commit: `f92e4d1a99ac326c7d2dfca54ca6f0e7ca66cadd`.
Tree: `4502ab54a89d39c8d30ce216de445ff07490941e`.
Uploaded evidence: `radar-r1-offline-20261111T071532Z-111267.json`.
SHA-256 of the exact uploaded bytes:
`72a92f114ed1141b746411fde16e4ce2a0bc2d516db10047ea1c7fc77a6461c5`.

- All five reported source hashes match the published, locally reviewed files.
- Python 3.14.6, SQLite 3.53.4: 44 tests, no failures/errors/skips.
- Runner status `offline-core-passed-live-blocked`; elapsed 0.600567 seconds.
  This is offline rehearsal duration, not a trading-latency benchmark.
- Synthetic capture: four messages/four rows/654 raw bytes; one restart with a
  gap after row two; terminal `message-limit` stop. The report records successful
  local restore/replay and source preservation.
- No network, credentials or paid collection were used by the acceptance runner.
  Off-machine restore, real-source initial state and ledger order, subscription
  installation, billing enforcement and profitability remain unverified.

Acceptance is based on the uploaded runner report and matching source hashes;
this review did not independently access Kali or its temporary raw fixture.
The report's static `remaining` list still includes Kali review; this acceptance
record resolves that item without modifying the original evidence.

Host setup correction: `/home/redeye/apps/solana-early-alpha-radar` was not a
usable Git checkout for the supplied fetch command. Validation used a new
independent review repository fetching the exact commit. Future commands must
not assume Git metadata exists in the running application directory.

This acceptance does not close the full R1 gate, authorize funding or live
collection, or clear PR/CI consolidation. Next: source feasibility and connection
coexistence, followed by separately validated transport and preservation work.
