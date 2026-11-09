# B1: baseline liquidity and 30-second quote research

Status: **design in progress; first evidence increment awaiting Kali acceptance**.
Started early on 9 November 2026 at the owner's request. The agreed B1 checkpoint
remains 16–27 November. This is a design record, not an experiment registration,
model freeze, G1 clearance or permission to collect a new validation set.

Based on accepted B0 commit `2c738d7511d3f5c2d854ba7c7eb0a9205880c7b6`.
The development branch starts there and excludes the unconsolidated E0 chain.
E0 remains blocked on retired-exposure reconciliation; its held state is separate.

## 1. Scope decision and alternatives

The [project agenda](PROJECT-AGENDA-20261108.md#9-b1--r1--g1--choose-the-smallest-informative-study)
preferred creation-trader/URI-hash hypotheses when coverage permits. B0 found a
full launch registry, no verified creator field and zero retained launch matches
for the 743 matched observer decisions in the supplied six-hour joined report.
These features cannot support a contemporaneous quote study from that evidence.
Historical reported traders are not verified creators or profitable wallets.

The permitted B0 lane is bounded offline quote research. Baseline has much better
recorded liquidity/security-clock coverage than early-activity or Fast30. Choose
one baseline-only hypothesis for feasibility; do not pool the cohorts, backfill
launch data, repair production capture, activate a feed or train an ML model.
Organic score, trader repetition and other horizons are not additional primary
hypotheses in this increment. This decision is based on coverage and accounting
interpretability, not a newly discovered return advantage.

## 2. One candidate question

**H1:** Among compatible, first-per-token baseline quote admissions, does selecting
the higher-liquidity half by recorded entry liquidity improve the mean 30-second
fixed-quantity quoted return over the same eligible baseline population?

The candidate rule is `entry liquidity >= discovery median`. Compute that median
once from feature-usable first admissions in the designated discovery set,
without outcome weighting; include ties, and report the resulting selection
fraction. If the rule selects everybody or nobody, it is uninformative: stop,
do not search alternative cutoffs. The median has **not** been fitted in B1's
initial coverage audit. It is a research threshold, not a safety/liquidity floor.

The comparator is all feature-usable first baseline admissions in the same
evaluation interval, not a randomized control or a separately sampled cohort.
Selected rows overlap that comparator. Any later uncertainty analysis must keep
that dependence and time/token clustering; an independent two-sample test is
inappropriate. Report the complementary rejected group descriptively without
treating it as a second primary hypothesis or searching for a replacement winner.
No inference is made about outcomes of quota-skipped signals.

## 3. Feature, population and quote contract

| Item | B1 design |
| --- | --- |
| Population | Baseline admissions under `three-cohort-budgets-v3`, verified `entry-features-1`; preserve all eligible/skip denominators |
| Token handling | Order by signal timestamp then sequence; take the first baseline admission per token **before** feature/outcome exclusions; never replace an unusable first admission with a later favorable one |
| Feature | Legacy `predictors.liquidityUsd`, positive and exactly matching recorded `entry-context-1` supplemental liquidity |
| Availability | Supplemental market clock must be `within-ttl`, nonnegative and equal to the legacy recorded market age; null/stale/invalid values remain excluded with reasons |
| Clock meaning | Scanner market-response observation stored before the immutable signal; this is local availability evidence, not the provider's measurement time or a guarantee of truthful/current liquidity |
| Security | Existing baseline evidence only; field presence and a TTL check are not token safety approval; no extra security optimization |
| Notional | Existing observer source requests 10,000,000 USDC atomic units, i.e. hypothetical 10 USDC; verify each original probe's amounts before outcome analysis |
| Horizon | 30,000 ms after buy response, using the existing validated on-time target contract; also retain signal-to-buy and actual sell request/response clocks |
| Route universe | Routes actually returned by the existing observer provider, with exact fixed token quantity; no DEX restriction, new route filtering or assumption that a scanner pool matches the returned route |
| Target | Existing validated on-time fixed-quantity quoted USDC change, conditional on a returned valid quote; unavailable/late/failed labels stay explicit, never zero |
| Migration | No migration-specific claim. Changed/unsupported or unquoted paths stay in denominators; do not retrospectively remove migrations on the basis of success/failure |

Source mapping: `scanner/src/core/radar.js` applies market observations;
`scanner/src/core/entry-context.js` captures immutable values and local ages;
`research-dataset/entry_context.py` validates supplemental context;
`research-dataset/build.py` builds entry predictors and separate targets;
`quote-observer/observer.mjs` fixes the hypothetical buy size;
`quote-observer/quote-check.mjs` quotes the fixed buy output quantity on exits.
The reduced coverage audit does not independently revalidate original quotes.

## 4. Existing evidence and preservation

The two accepted B0 derived captures overlap. Their compressed hashes are pinned
in `research-dataset/b1_design_audit.py`; changed or different files stop the audit.
Inputs are bounded at 64 MiB compressed/decompressed each and 20,000 unique rows.
The script checks source/entry identity, deduplicates its explicit entry projection,
counts policy/feature eligibility and writes a private new report without overwrite.
It does not access target values, quote availability or pricing fields for analysis.
This does not erase prior human inspection of those outcomes.

Local reproduction on 9 November:

| Evidence unit | Count |
| --- | ---: |
| Unique eligible records across cohorts | 11,694 |
| Duplicate entry projections removed | 8,111 |
| Baseline eligible records | 896 |
| Baseline admissions / distinct admitted tokens | 141 / 141 |
| Feature-usable first baseline admissions | 141 |
| Early-activity admissions, outside H1 | 166 |
| Fast30 admissions, outside H1 | 165 |

Baseline signal-day counts: November 5: 34; November 6: 40; November 7: 40;
November 8: 27. Only November 6 and 7 are fully contained UTC days in the requested
observer-detection window union. Query coverage does not prove uninterrupted
operation or complete signal-time coverage. Distinct tokens are not independent
observations when market/day effects are shared.

Expected deterministic entry-projection SHA-256:
`d2db8032e9aa206f51b861c87ac09269485a49b6e769b7e97630e95be58059da`.
This hashes only the selected entry fields, not outcomes or the full source ledger.

Retain both original `capture/` directories, indexes and derived reports together.
Their B0 local provenance was accepted; no new off-machine restoration was verified.
Seven-day live retention is not study preservation. Before any new study, its
capture cadence, byte budgets, retention, restart/gap handling and recoverable
copies must cover the entire fixed study plus maturity period. No new scheduled
job, backup change or prospective collection is installed by B1.

## 5. Analysis boundaries and cost accounting

Both supplied captures and the old closed/insufficient studies are discovery-only
for this question. No split of these already inspected November files creates an
untouched validation set. Do not reopen old registrations or call old holdouts new.

Before any outcome comparison, replay the retained original probes using the
existing builder, verify notional/route/quantity/timestamps, reconcile exclusions,
and log this H1 with all previously inspected evidence. The first B1 increment
only audits entry coverage; it makes no return comparison or superiority claim.

For subsequent bounded discovery, compute the once-fixed median and one primary
descriptive contrast: mean selected quoted return minus mean comparator quoted
return. Report absolute selected mean/median, all admission/feature/quote-state
denominators, day/token concentration, quantiles, worst result, losses of at least
50%, and removal of the best token and best UTC day. These are diagnostics, not
additional hypotheses. With two complete days, do not issue an evidential
confidence claim or infer a powered fresh-trial sample size.

Quoted output already reflects the quoted route's embedded amount effects.
Do not subtract reported price impact/platform fees a second time. An explicit
**illustrative** extra-cost sensitivity can subtract 0, 0.20 and 0.60 USDC from a
10-USDC returned-quote round trip (0, 2 and 6 percentage points of return). This
is a flat additive stress, not measured execution cost or an assumed live fee.
Show the break-even additional USDC cost and retain negative values as negative.
Failed/pending buys or exits cannot be priced as successful liquidations; keep
their count and economic uncertainty separate. Rent funding, recoverable rent and
irrecoverable fees must stay separate in a later executable cost contract.

Before G1 held-out analysis, freeze an evidence-backed cost model, downside and
coverage thresholds, required improvement, confidence method, fixed interval,
sample/maturity guards and treatment of unresolved execution. Those numerical
acceptance choices remain **unapproved and unset**, including the developer's
300-entry / 90% / -2% proposals. A favorable illustrative stress does not satisfy
them. Better than a losing comparator is insufficient: the later gate also needs
positive absolute modeled net economics under the agreed cost assumptions.

## 6. B1 completion criteria and current disposition

| Decision | Current disposition |
| --- | --- |
| Entry feature technically usable for a small exploration | Local evidence supports it; pinned Kali reproduction pending |
| Launch-trader/URI quote hypothesis | Blocked by B0 coverage; no paid-feed activation proposed |
| Fresh holdout available in the supplied files | **No-go**: previously inspected evidence and insufficient independent time coverage |
| Claim of economic edge / ML readiness | **No-go**: this increment has not analyzed H1 outcomes or established costs/power |
| Whole B1 phase acceptance / consolidation | Open; this increment alone does not close B1 |

B1 closes with a reviewed design and either a justified next study scope or an
explicit infeasibility decision. Remaining work is (1) Kali acceptance of this
coverage audit, (2) raw-probe/preservation feasibility for H1, and (3) one bounded
cost/sampling/split specification with an exploration budget and go/no-go decision.
Any candidate revision must be logged; do not silently add predictors or optimize
cutoffs. Where genuinely untouched later historical data exist, fix temporal
boundaries before retrieving outcomes, purge overlapping tokens across cohorts,
require label availability before the boundary and retain the existing five-minute
embargo. Otherwise a separately approved fresh study is required. Never relabel
the current 141 tokens as a held-out test.

## 7. Agenda and ML work

| Checkpoint | Deliverable / condition |
| --- | --- |
| November 9 (early B1 start) | Candidate contract and outcome-independent coverage reproduction; this increment |
| November 16–27 | Finish B1 cost, sampling and preservation feasibility; one justified scope or a reasoned no-go |
| November 20 | E0 blocked-state checkpoint, unless materially new reconciliation evidence arrives |
| November 30–December 4 | Only a specifically justified R1 missing-data feasibility task; otherwise use existing-data lane |
| December 7–18 | Bounded discovery/eligible held-out assessment, conditional on accepted design and usable evidence |
| December 21–31 | C1 scope decision; no forced positive result or promised trading launch |
| 2027, conditional | Separately frozen fresh validation; calendar duration and sample guards determined before starting |

Dates retain the agenda's unconfirmed planning assumption of 24–32 focused hours
per week and Kali feedback in 24–48 hours. Starting early does not guarantee an
earlier gate closure. The baseline's observed 40 admissions on each of two full
days is capacity evidence only; a median filter, repeats, missingness, token purge
and clustering reduce usable evidence. Do not convert it directly into power.

**ML:** no installation, training, retraining or promotion is needed now. H1 is a
single interpretable rule. Old frozen models/protocols remain unchanged. A model
would need a separately justified target, usable labels and stronger evaluation
than this initial sample permits.

## 8. Kali validation of this increment

Use the exact development commit supplied with the release. Run all
`research-dataset` tests with `ResourceWarning` treated as an error, then run
`b1_design_audit.py` against the two preserved B0 derived reports. The host command
must verify a clean pinned checkout and capture its Python version and audit log.
Expected: all tests pass; the entry projection above, 11,694 unique records,
8,111 duplicates, 141 feature-usable first baseline admissions and exactly the two
complete requested dates match. All gate, registration, training and live-use
flags remain false. An absent or changed input stops; do not substitute a fresh
capture under the old evidence identity.

Development publication is allowed for this check. No PR, CI dispatch, merge or
deployment is authorized by it. No Docker restart, network quote request, wallet
access or modification of the live scanner/observer is required.
