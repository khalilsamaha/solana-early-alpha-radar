# H1 bounded offline discovery

Implementation phase starts from B1 merge `a4199f55d7cb5a8d0bd73d1a550b16cd7909eeb7`.
The [accepted design](B1-QUOTE-STUDY-DESIGN-20261109.md) remains authoritative.
This phase may proceed independently of E0's blocked operational state.

Before inspecting the H1 comparison, fix these reporting details:

- Read exactly the two hash-pinned B0 reports. Require full duplicate-row equality,
  including outcomes; never choose the better of overlapping records.
- Choose the first baseline admission per token before exclusions. Fit the median
  once from all feature-usable first admissions, including those without usable
  outcomes. Select liquidity greater than or equal to that median, retaining ties.
- Use only validated, on-time 30-second fixed-quantity returns. Missing/late/failed
  outcomes remain counted and are never imputed. Other horizons cannot be selected.
- Quantiles use linear interpolation at 5%, 25%, 50%, 75% and 95%.
- Remove the best selected token by highest usable return; break ties by signal
  time and sequence. Remove the best selected UTC day by highest mean usable
  selected return; break ties by date. Remove the same token/day from both the
  selected set and its overlapping comparator, without refitting the threshold.
- Show each group's admission and label counts per day, maximum day share, unique
  token count, positive-return contribution concentration, tail losses and all
  three fixed illustrative cost stresses. No confidence interval or power claim.
- The final CLI also requires both original capture directories. Replay each
  with the existing builder and require complete equality to its pinned report.
  Retain original request/response clocks and quantities in the private output.
  A derived-only local preview cannot count as this raw replay or Kali acceptance.

Existing source bounds and private, exclusive output publication apply. Read saved
files only; no database, RPC, quote request, provider/feed change or transaction.
All study-registration, model, gate and live-use flags remain false. Source pushes
are for Kali review; no PR or CI dispatch until this complete phase is accepted.

The same maximum two focused engineering days applies. Negative or uninformative
results close this candidate's exploration; do not search replacements here.

## Accepted outcome and combined consolidation

Kali accepted source `a980b497aad73488f54832d59c38da0ef80f27b9` on November 10:
all 64 dataset tests passed, both pinned original captures replayed, and the full
report matched its logged canonical digest
`8c24eca0c448515fa2c0f91bed4034762c6392117e6648e1cea33286b7f4d94f`.
The 71 selected of 141 baseline tokens averaged -1.505907% quoted change versus
-2.560539% for the overlapping comparator, before illustrative extra costs.
This is a negative absolute-economic discovery result; no trial, model promotion
or trading activation follows. The candidate remains closed without retuning.

The owner's requested combined package is this unchanged H1 implementation plus
[the early C1 scope decision](C1-SCOPE-DECISION-20261110.md). Its documentation
acceptance and subsequent full-phase consolidation remain separate from the
already accepted H1 test/replay evidence. E0 remains outside this package.
