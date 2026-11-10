# B1: baseline liquidity and 30-second quote research

Status as of 10 November: **design decision complete; final documentation acceptance
on Kali pending**. Coverage and original-capture replay are accepted on Kali.
Started early on 9 November 2026 at the owner's request. The agreed B1 checkpoint
remains 16–27 November; it is not a mandatory waiting period. This is a design record, not an experiment registration,
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

Local reproduction on 9 November, accepted on Kali on 10 November:

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
Their B0 local provenance was accepted. Kali replay on 10 November rebuilt both
complete reports with identical JSON and identical compressed hashes. The pinned
source was `3af84cb76a2a64cd3b79b7da209a15dffdc93e96`, Python 3.14.6; all
51 dataset tests had passed on that source. No off-machine restoration was verified.
Seven-day live retention is not study preservation. Before any new study, its
capture cadence, byte budgets, retention, restart/gap handling and recoverable
copies must cover the entire fixed study plus maturity period. No new scheduled
job, backup change or prospective collection is installed by B1.

## 5. Analysis boundaries and cost accounting

Both supplied captures and the old closed/insufficient studies are discovery-only
for this question. No split of these already inspected November files creates an
untouched validation set. Do not reopen old registrations or call old holdouts new.

The retained-original replay prerequisite passed on 10 November using the existing
builder's amount, clock, quantity and return validation. All classifications and
exclusions matched the accepted originals, including failures. This H1 and its
previously inspected evidence are recorded here before any H1 outcome comparison.
No liquidity threshold has been fitted and no H1 superiority claim has been made.

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
| Entry feature technically usable for a small exploration | Accepted on Kali, including complete original-capture replay |
| Launch-trader/URI quote hypothesis | Blocked by B0 coverage; no paid-feed activation proposed |
| Fresh holdout available in the supplied files | **No-go**: previously inspected evidence and insufficient independent time coverage |
| Claim of economic edge / ML readiness | **No-go**: this increment has not analyzed H1 outcomes or established costs/power |
| Design recommendation | Go for the bounded discovery specification below; no-go for G1/R7 validation now |
| Whole B1 phase acceptance / consolidation | Final design ready for pinned documentation acceptance on Kali; no PR/CI/merge yet |

B1 closes with a reviewed design and either a justified next study scope or an
explicit infeasibility decision. Coverage and raw replay are accepted. Sections
9–12 complete the bounded cost/sampling/split/preservation decision. Only final
design acceptance remains for B1; later-study prerequisites are not relabeled as
completed B1 implementation or reasons to repeat accepted tests.
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
| November 10, earlier than planned | Final B1 design decision prepared; pinned documentation acceptance remains |
| November 16–27 | Original B1 checkpoint retained; advance earlier once final phase acceptance is complete |
| November 20 | E0 blocked-state checkpoint, unless materially new reconciliation evidence arrives |
| November 30–December 4 | Only a specifically justified R1 missing-data feasibility task; otherwise use existing-data lane |
| December 7–18 (original window) | Bounded discovery may start earlier after B1 acceptance; an untouched held-out check remains unavailable in the supplied files |
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

## 8. Accepted Kali validation of the implementation

The 10 November host check used the exact development commit, ran all
`research-dataset` tests with `ResourceWarning` treated as an error, and ran
`b1_design_audit.py` against the two preserved B0 derived reports. The host command
verified a clean pinned checkout and captured its Python version and audit log.
Accepted: all 51 tests passed; the entry projection above, 11,694 unique records,
8,111 duplicates, 141 feature-usable first baseline admissions and exactly the two
complete requested dates matched. All gate, registration, training and live-use
flags remain false. An absent or changed input stops; do not substitute a fresh
capture under the old evidence identity.

Development publication is allowed for this check. No PR, CI dispatch, merge or
deployment is authorized by it. No Docker restart, network quote request, wallet
access or modification of the live scanner/observer is required.

## 9. Final cost decision

For the next discovery task use only version `b1-flat-extra-usdc-stress-1`:

`conditional net quote return (%) = validated quote return (%) - 100 * C / 10`.

Here C is a hypothetical extra irrecoverable round-trip cost in USDC, fixed at
0, 0.20 and 0.60 for descriptive sensitivity. The zero case is the raw quoted
reference, not a claim that trading is free. The latter cases subtract 2 and 6
percentage points respectively. Do not optimize C or select which scenario to
report after seeing outcomes. All three and the break-even extra cost are shown.
Uniform C cancels in the selected-minus-comparator contrast: cost stress can change
absolute economics, but cannot create evidence that the liquidity rule is better.

| Cost/effect | Handling |
| --- | --- |
| Embedded route amount effects and provider-reported impact/fees | Keep quoted amounts; do not subtract them again |
| Network fee, priority fee, tip or other external charge | No measured live estimate asserted; included only to the extent of an explicitly illustrative C; later measured model must establish mutually exclusive components |
| Account rent | Funding requirement separate from irrecoverable cost; recoverability/timing unknown here |
| Failed buy, failed/late/missing exit, unresolved inventory | Separate counts and unknown economic effects; no zero-return imputation or multiplication of availability by conditional return |
| Market movement, liquidity provider measurements, actual landing | Quote evidence only; no execution/slippage inference |

Discovery can reject a candidate whose conditional results are unattractive even
before extra costs. It cannot approve execution economics: no calibrated live
costs, unresolved-exit loss model or approved economic/downside limits exist.
That is a **no-go for validation/promotion now**, not a reason to invent default
loss tolerances. No owner capital or transaction budget is needed for this offline task.

## 10. Sampling and evaluation decision

The forecast uses the existing observer's 48/day baseline ceiling and its observed
40/day on each of two complete UTC days. Admission is first-available under quotas,
spacing, concurrency and mint suppression; inclusion probabilities are unknown.
No inverse-probability weighting or inference to all 896 eligible records is valid
from these data alone. The study target remains admitted baseline opportunities.

For planning only, let A=40 admissions/day, s=0.5 selected fraction, and u be the
fraction surviving feature requirements, first-token/purge exclusions and valid
labels. Expected selected labelled rows/day = A*s*u. Ties can make s differ from
0.5; future distribution and A/u may change. None of these scenarios estimates power.

| Illustrative u | Selected labelled rows/day | Rows in 21 days | Days for 2,000 rows (rounded up) |
| --- | ---: | ---: | ---: |
| 1.0 | 20 | 420 | 100 |
| 0.6 | 12 | 252 | 167 |
| 0.3 | 6 | 126 | 334 |

The 21-day and 2,000-row examples are calendar arithmetic, **not trial duration or
sample-size requirements**. Token uniqueness does not remove market/day dependence.
No effective sample size or powered minimum can be derived responsibly from two
complete days. A later design must specify its minimum meaningful effect, downside,
missingness limits and dependence-aware uncertainty before inspecting validation
outcomes; the current decision does not approve numerical substitutes.

For bounded discovery use the full, deduplicated pair of already inspected reports
as one exploratory sample. Fit the one feature-only median once, then compute the
one contrast and diagnostics in section 5. Do not manufacture a train/test split
of these files. Track exclusions before looking at outcomes, keep source+sequence
identity and full duplicate conflicts explicit, and never replace a first token
admission because its quote failed. No feature/threshold/horizon search is allowed.

There is currently **no approved untouched evaluation interval**. Later historical
data are not presumed unseen merely because they are absent here. A new evaluation
would require an exposure inventory, locked code/rule/cost/protocol, token purging
against discovery across cohorts, label-availability cutoffs and at least the
existing five-minute embargo. If unseen evidence cannot be established, use a
separately registered fresh trial only after its other prerequisites pass. Fix the
end and maturity rules in advance; no extension until positive, outcome-based
interim tuning, or reopening of closed studies.

## 11. Preservation decision

**Existing-data discovery is feasible now:** retain both accepted capture indexes,
all 24 original chunks, both derived reports, the accepted log/report identities,
the exact code and this design. Overlap is intentional; records are deduplicated,
not counted twice. Read originals only; publish separate new outputs without overwrite.
Do not delete originals when derivative reports are produced.

**Fresh-study preservation is not operationally accepted.** The live ledger has
seven-day retention. `operations-tools/quote_backup.py` retains the newest 14 local
archives after successful required verification; those are 14 archives, not a
guaranteed number of calendar days. Therefore neither the live ledger nor rotating
local backups alone preserves a multi-week trial. The old availability-study
preserver is tied to its own closed registration and must not be reused as a new trial.

The following is a proposed future engineering specification, not an installed
schedule or authorization to collect/register a trial:

- Capture original observer evidence once per 24 hours with a 48-hour lookback,
  using eight six-hour chunks and the existing capture-only path. Overlap covers
  boundary labels and supports exact deduplication. Record each source version,
  window, snapshot cutoff, clocks, counts, checksums and any capture failure.
- Preserve all cohorts' entry identities for cross-cohort token purging. Never
  drop failed/unfinished/skipped records from the capture to save space. Interim
  reports expose coverage/integrity only, not comparative outcomes.
- Keep the existing 60-second read transaction, 32-MiB WAL-growth bound, row and
  96-MiB raw-capture limits, 512-MiB ledger/restore limit and 180-second wrapper
  deadline. Stop on a cap; do not raise limits or silently narrow the window.
- A missed daily capture is an incident. Before retention expires, explicitly
  assess whether retained windows can fill the gap with the existing bounded
  tooling. Never infer uninterrupted capture or interpolate missing opportunities.
  An unrecoverable gap remains a protocol deviation and can make the trial insufficient.
- Store study captures separately from rotating backup paths. Retain through the
  fixed study end, label maturity, final review and a documented retention decision;
  do not automatically delete them at seven days or after 14 backups.
- Before registration, demonstrate checksum-verified isolated restoration and
  replay from an off-machine study copy, including a missed-capture/recovery test.
  Current source support for optional cloud backup is not proof of a current
  successful off-machine restore. No cloud upload/download is performed by B1.
- Before the fixed endpoint, reserve a final capture after the separately frozen
  maturity allowance; preserve unresolved labels rather than waiting for favorable
  completion. Actual deadlines and clock states decide maturity, not wall time alone.

Capacity estimate: the larger accepted 72-hour raw capture is 51,767,700 bytes,
about 17.3 MB/day for **all** captured evidence. A 48-hour overlapping daily capture
would be about 34.5 MB/run if this rate persisted, roughly 1.1 GB for 31 captures.
At the current raw cap, 31 captures could approach 3.2 GB before indexes, derived
reports, archives and temporary restore space. These are planning estimates, not
disk reservations or a chosen trial length. Measure actual compressed bytes and
free space before any deployment; reserve separate workspace for bounded restores
and never consume live-service headroom. Neither export caps nor costs are lifted.

## 12. Final B1 disposition and next engineering phase

**GO:** implement and validate one offline H1 discovery report against exactly the
two accepted, overlapping historical captures. Maximum two focused engineering
days for implementation, tests and interpretation; this is an effort cap, not a
promise of unattended calendar work. If this scope cannot fit the cap, return a
specific blocker and revised estimate instead of expanding it. Incremental feed
and transaction spend: zero. No R1 feed purchase or ML environment change is needed.

The deliverable must preserve original identities and exclusions; fit only the
specified median; reproduce the fixed 10-USDC/30-second target; show the comparator,
the three fixed cost stresses, missingness and token/day/tail sensitivities; and
remain explicitly exploratory with all promotion/registration/live-use flags false.
A negative or uninformative result closes this candidate's bounded exploration;
do not optimize a replacement in the same report. An apparently positive result
is only a candidate for separately justified evidence and evaluation design.

**NO-GO now:** G1 clearance, fresh R7 registration, claimed economic edge, trained
or promoted ML, or live/funded execution. Blocking prerequisites are an untouched
evaluation path, defensible sample/dependence specification, agreed economic/risk
limits and evidence-backed costs, and accepted fresh-study preservation. No claim
is made that these prerequisites will all become feasible by a particular date.
This is a valid B1 design conclusion, not completion of those downstream gates.

The final change from Kali-accepted `3af84cb` is documentation only. Validate its
exact pinned revision and documentation diff on Kali; retain the accepted 51-test
log and byte-identical replay evidence for the unchanged implementation. Do not
rerun those checks merely to fill a new increment. Once this whole B1 design phase
is accepted, perform the required full repository and applicable research-suite
checks for consolidation, followed by reviewed CI/PR and any required merge
approval. No PR, CI dispatch or merge has been performed for this final design.

There is no need to wait for November 27, November 30 or December 7 to start a
ready next engineering phase. Advance the bounded discovery work after B1
acceptance, preserving the agreed gate order. The original dates remain review
checkpoints; fresh observation time cannot be compressed by finishing code early.
E0's November 20 blocked-state checkpoint and all operational holds remain separate.
