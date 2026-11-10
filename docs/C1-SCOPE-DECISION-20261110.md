# Early C1: scope and feasibility decision — 10 November 2026

Status: **review complete; pinned documentation acceptance on Kali pending**.
This is the early C1 scope decision requested after H1. The December 31 owner
scope/budget checkpoint remains; this document does not mark G1, R7 or G2 passed.
No new study, spending, product pivot or operational action is registered here.

Source baseline: H1 `a980b497aad73488f54832d59c38da0ef80f27b9`, descended from
B1 main merge `a4199f55d7cb5a8d0bd73d1a550b16cd7909eeb7`. H1 implementation,
its test file and all frozen protocols/artifacts remain unchanged. This decision
and H1 will share one consolidation after applicable Kali acceptance.

## 1. Decision

**Do not advance the H1 liquidity candidate to a new trial or promotion.** Its
Kali-accepted analysis has negative absolute quoted economics before extra costs.
The positive selected-minus-comparator difference does not satisfy economic
readiness. This closes that bounded exploration; no threshold or horizon search.

Assess exactly one alternative: **research-only screening of provider-reported
30-second exit-quote failures in admitted early-activity watches**, using the
existing frozen legacy availability model and its existing 0.5 threshold. This
is a narrow quote-availability question, not a general token safety, rug,
unsellability, execution-success or profitability classifier.

Disposition of the alternative:

- **Technically plausible to reuse existing components** for a separately designed
  future observation study. The target, model interface, entry fields and bounded
  capture/evaluation components already exist. This is not empirical acceptance.
- **No-go for starting another trial now.** The old confirmation remains
  insufficient; no untouched evaluation interval or accepted new-study
  preservation is established; decision-use tolerances and a dependence-aware
  evaluation/sample contract for a new study are not agreed.
- **No paid-feed R1 spike justified now.** The candidate's input fields are already
  represented. No identified new-feed field would resolve the actual blockers.
  Reopen R1 only for a specific essential missing fact with a capped acquisition
  proposal; do not build a broad indexer or wallet-reconstruction system.
- **No new fit, threshold search, extra research lane or live filter.** Keep this
  as one possible future research alternative. If its prerequisites cannot be
  justified, pause additional alpha experiments rather than repeatedly reuse the
  same inspected samples. Existing operations and E0 reviews continue unchanged.

## 2. Why this alternative, and what the earlier evidence says

The alternative predates H1's result. It is selected because the repository
already contains an exact frozen model, an explicit label contract, a replayed
review and a separate prospective confirmation. It is not chosen after testing
several replacements on H1's 141 baseline tokens.

| Evidence | Established result | Meaning for this decision |
|---|---|---|
| Completed October frozen review | Early-activity availability lead: excluded 20 of 63 provider failures and retained 218 of 218 returned quotes at the unchanged threshold | Historical motivation only; inspected development evidence, not a new validation set |
| Separate October 30–November 6 confirmation | 304 predictions, 302 known labels, seven UTC dates; 15 excluded known labels against a required 20 | **Insufficient**, not passed; do not extend or relax the fixed study |
| Same confirmation, descriptive | Excluded 14 of 45 provider failures; retained 256 of 257 successful quotes | A useful question remains, but effectiveness and false exclusions are not accepted by these counts alone |
| Same confirmation, selected returned quotes | Mean -7.18% at 30s and -13.89% at 120s | Availability discrimination does not establish positive economics |
| H1, accepted on Kali November 10 | 71/141 selected; mean -1.505907% versus -2.560539% comparator; worst selected -54.14932% | H1's economic no-go stands; do not transfer its baseline rule to early-activity |

Earlier-study figures are taken from their committed accepted decision records,
not newly rerun from the original private experiment in this review. Do not
multiply availability probabilities by quoted returns to claim net profitability.
The insufficient confirmation is not a negative prospective economics iteration;
H1 is inspected-data discovery, not a prospective G2 trial. The agenda's rule about
two negative prospective iterations is therefore not triggered by these two items.

## 3. Candidate boundary and compatibility

Potential intended use: a research triage warning about the defined quote outcome.
Whether that warning is useful enough to justify another study is an owner scope
choice; deployment or a commercial risk-screen product is not approved here.

| Contract | Existing boundary to preserve in any proposal |
|---|---|
| Population | Admitted early-activity watches under `three-cohort-budgets-v3`; no claim about unquoted or skipped signals |
| Candidate | Original frozen legacy availability model; preserve exact artifact, preprocessing and coefficient identity; 0.5 threshold |
| Inputs | Recorded entry `return30sPct`, `return60sPct`, `lastIntervalReturnPct`, `averageReportedTradeUsd`; frozen missing indicators/imputation remain unchanged |
| Target | Validated on-time fixed-quantity 30s quote = 1; HTTP 400 provider-reported quote-generation failure after a validated buy = 0 |
| Unknowns | Transport/service failures, missing/late/pending observations and invalid/no validated buys remain separate; never recode as token unsellability or zero return |
| Primary diagnostic | Fraction of provider-reported failures excluded, paired with successful quotes retained and unknown rates in both partitions |
| Comparators | Same-case no-screen availability counts and original frozen training-rate constant for probability metrics; no newly fitted competitor |
| Economics | Separate requirement if anyone proposes trading use; quote discrimination is not an economic edge |

This review checked entry-only compatibility on the two hash-pinned B0 reports.
It did **not** compute alternative-model predictions, read target labels for a new
comparison, fit weights, search thresholds, or inspect a new date interval.

| Entry-only inventory | Count |
|---|---:|
| Deduplicated early-activity eligible records | 6,517 |
| Admitted / distinct first-admission tokens | 166 / 166 |
| First admissions compatible with existing `forward-study/audit.py:eligibility` | 166 |
| Nonmissing recorded `return30sPct` among those 166 | 125 |
| Nonmissing `return60sPct` / `lastIntervalReturnPct` / `averageReportedTradeUsd` | 166 / 166 / 166 |
| First admissions by signal UTC day, Nov 5 / 6 / 7 / 8 | 40 / 47 / 46 / 33 |

Only November 6 and 7 are complete **requested detection-window** UTC days;
that does not prove continuous uptime or full signal-time coverage. Recorded
presence is not a freshness, correctness or predictive-value verdict. Missing
30s entry values remain missing; do not add a complete-case exclusion to the
frozen model. Compatibility is before original-training/development token purges,
which were not recomputed here. These 166 are not a future usable-sample forecast.

The two reports have already been inspected, overlap old study dates and have
only a short span. No split, relabelling or nominal new registration turns them
into an untouched validation set. No future sample size or duration is inferred
from the 47/46 daily admission counts or the old 15 excluded labels.

Input compressed SHA-256 identities remain those in `b1_design_audit.HASHES`.
The C1 entry-only projection hash is
`1c92e1f24b949bf3b978d4f7a3e0f73a76e80056f67b8a5ea5d82fcf999c61f1`.
The reproducible entry-only calculation is included below; output/target fields
are excluded from the projection. This is a documentation review, not a new
production audit command or a new experiment artifact.

## 4. Reopen conditions and effort limits

| Required before a new trial | Concrete evidence / decision needed |
|---|---|
| Useful decision | Agree the intended research warning and the trade-off between missed provider failures, falsely excluded successful quotes, and unknowns. Numeric tolerances remain unset. |
| Frozen identity and compatibility | Verify the preserved private artifact and old registration identities on Kali; inventory excluded tokens from all exposed studies/captures, including the confirmation and later inspected evidence. Existing old registration cannot simply be reused. |
| Untouched evaluation | A separately fixed future interval, code/rule/protocol identity, cross-cohort token purge, at least five-minute embargo where applicable, fixed endpoint/maturity and no outcome-based extensions |
| Statistical and coverage contract | Specify effect/decision threshold, paired/dependent uncertainty, independent time coverage, sample/rare-label guards and unknown handling before outcomes. Old 200/20/7 guards are historical, not power or automatically approved new requirements. |
| Evidence preservation | Bound capture bytes/rows/disk and restart/gap behavior; demonstrate checksum-verified off-machine restore/replay for the new study. Seven-day ledger retention and 14 rotating archives do not establish this. |
| Separate authorization | Review the complete new study proposal and its resource budget before registration; paid services, deployment and funded actions remain separately scoped. |

A concrete next proposal, if this alternative is chosen, should first limit
metadata-only artifact/exposure/preservation inventory to **one focused engineering
day**, zero incremental feed/transaction spend, and no predictions or new outcome
reads. That is a proposed follow-up cap, not a task started by this decision.
It must return identities, unknowns and a preservation gap list or stop as blocked.
Only then estimate the necessary preservation/evaluator changes. Do not promise a
seven-day, 21-day or 2,000-row new study before the above choices are made.

If the warning has no agreed useful decision, the artifact cannot be reconciled,
or preservation and sample requirements cannot fit a justified budget, record
**deferred/pause**. Do not automatically switch to wallet, creator, URI or slower
horizon strategies. E0 is not the blocker for this feasibility review, and its
resolution would not fix the alternative's evidence gaps.

## 5. Combined delivery and checkpoints

1. H1 code and its 64-test/raw-replay Kali acceptance remain unchanged and accepted.
2. Accept this early C1 scope document and H1 closure note on Kali: exact parent,
   documentation-only diff, file hashes and existing source/package check. Do not
   rerun H1 outcomes or its 64 tests solely for these prose additions.
3. Once accepted, consolidate **H1 + early C1** as one phase package: full existing
   regression partitions, separate applicable research suites, reviewed PR/CI,
   explicit main-merge approval and post-merge verification.
4. No PR/CI or merge is performed by publishing this documentation increment.
   E0 code/journals stay outside the combined package.

| Checkpoint | Updated position |
|---|---|
| November 10 | H1 negative discovery accepted; early C1 scope review completed ahead of the original window; documentation acceptance pending |
| November 13 baseline review | Review current operational evidence when work resumes; no new live health claim is made here |
| November 20 E0 | Existing daily read-only review and blocked-state/closure checkpoint unchanged |
| November 30–December 4 R1 | Conditional only; no new-feed spike justified by the chosen alternative today |
| December 31 C1 owner checkpoint | Retained for scope/budget decisions; no forced registration or trading launch |

No model installation, training, refit or promotion is needed for this decision.
The original calendar is a review framework, not an instruction to wait when a
bounded scope decision can be completed early.

## 6. Sources and entry-only reproduction

- [Agenda](PROJECT-AGENDA-20261108.md), especially sections 9, 11 and 12.
- [Frozen review decision](FROZEN-REVIEW-DECISION-20261028.md).
- [Closed availability confirmation](EXIT-RPC-SESSION-20261106.md#closed-availability-study).
- [Existing availability protocol](../availability-study/protocol.json) and
  [confirmation code](../availability-study/confirmation.py).
- [Feature compatibility](../forward-study/audit.py),
  [frozen legacy inputs](../forward-study/model.py) and
  [quote-state classification](../research-dataset/exit_availability.py).
- [B1 design](B1-QUOTE-STUDY-DESIGN-20261109.md),
  [H1 implementation and acceptance](H1-DISCOVERY-20261110.md).

From the reviewed repository root, pass the exact existing live and backup derived
report paths as the two positional arguments. No model or target is evaluated:

```python
# python3 -B - LIVE_REPORT BACKUP_REPORT < this snippet
import sys, collections, json, hashlib
from pathlib import Path
sys.path.insert(0, 'research-dataset')
import b1_design_audit as b
sys.path.insert(0, 'forward-study')
from audit import eligibility
reports = [b.read_pinned(Path(sys.argv[1]), 'live'),
           b.read_pinned(Path(sys.argv[2]), 'backup')]
coverage = b.audit(reports)
fields = ('return30sPct', 'return60sPct', 'lastIntervalReturnPct', 'averageReportedTradeUsd')
rows = {}
for report in reports:
    for row in report['rows']:
        item = {k: row[k] for k in ('id', 'seq', 'mint', 'signalAt', 'utcDay', 'cohort', 'decision')}
        item.update(eligibility=eligibility(row),
                    features={k: row['predictors'].get(k) for k in fields})
        if item['id'] in rows and rows[item['id']] != item:
            raise ValueError('Conflicting entry projection')
        rows[item['id']] = item
admitted = sorted((r for r in rows.values() if r['cohort'] == 'early-activity'
                   and r['decision'] == 'admitted'), key=lambda r: (r['signalAt'], r['seq']))
seen, first = set(), []
for row in admitted:
    if row['mint'] not in seen:
        seen.add(row['mint'])
        first.append(row)
compatible = [r for r in first if r['eligibility'] == 'compatible']
print('eligible', sum(r['cohort'] == 'early-activity' for r in rows.values()))
print('admitted/first/compatible', len(admitted), len(first), len(compatible))
print('days', dict(collections.Counter(r['utcDay'] for r in first)))
print('present', {f: sum(r['features'][f] is not None for r in compatible) for f in fields})
print('complete requested days', coverage['completeRequestedUtcDays'])
raw = json.dumps(sorted(rows.values(), key=lambda r: r['seq']),
                 sort_keys=True, separators=(',', ':')).encode()
print('projection SHA-256', hashlib.sha256(raw).hexdigest())
```
