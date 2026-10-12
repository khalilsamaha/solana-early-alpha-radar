# Price reconciliation audit — 11 October 2026

This read-only report update investigates why original-pool paper prices and walletless quoted proceeds disagree. It does not change scanner rules, polling, notifications, quote admissions, paid subscriptions or trading behavior. No installation, rebuild or restart is needed.

## Run on Kali

Fetch `feature/price-reconciliation-20261011` into the development checkout and detach at the exact commit supplied with this release. Then:

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/launch-study/run-joined.sh --hours 6
```

Upload the printed `radar-launch-quotes-*.json.gz` file. The original joined analysis remains under `analysis`; the new audit is under `reconciliation`. The console prints counts of paired observations, opposite return signs and large discrepancies with close local receipts and reported original-pool routes. Collection continues throughout. The new source projection reads existing immutable research-entry history, so retained historical entries can supply evidence immediately; no overnight collection is required.

To audit the already supplied export entirely offline:

```bash
cd ~/apps/solana-early-alpha-radar
python3 ~/apps/solana-radar-dev/launch-study/joined_report.py \
  --input radar-launch-quotes-20261011T200035Z-3147237.json.gz \
  --output "radar-price-reconciliation-replay-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

Older exports omitted entry history. Offline replay correctly labels that history `not-exported`; a fresh database read is needed to include it. Replays recompute both analyses, ignoring uploaded derived summaries. Existing input files are never overwritten.

## What the audit measures

1. **Entry reference.** Preserve the paper entry price and up to 24 price/time samples from its immutable same-pool history. Validate ordered positive-price samples received no later than the entry. Compare the latest sample price to the recorded entry price. Where available, cross-check the independently projected observer receipt timestamp and its field provenance. Invalid or contradictory receipts remain unknown. A matching history value confirms recorded consistency, not exchange freshness.
2. **Endpoint reconciliation.** At 30, 60 and 120 seconds, retain validated paper checkpoint prices, quoted changes, local sample/quote-response timestamps, actual receipt differences, route membership, lateness and provider failures. Return differences use percentage points, not relative percentages. An absent, missing or gapped paper observation never becomes a paired return.
3. **Remove the original entry reference.** Compare paper price at 60/120 seconds against paper price at 30 seconds; separately compare quoted USDC proceeds at 60/120 seconds against proceeds at 30 seconds for the same fixed token quantity. This arithmetic requires no token decimals. Both endpoints must already be valid. The result is a comparison of two paths, not a new simulated trade, optimal exit or strategy return.

The diagnostic protocol uses a 20-percentage-point discrepancy threshold and five-second local-receipt tolerance. The strict endpoint count also requires reported original-pool membership on both buy and sell, request delay at most five seconds, and quote response time at most eight seconds. Rebased strict counts check original-pool membership and receipt/timing criteria on both sell endpoints. All other paired observations remain visible. These thresholds organize investigation; they are not eligibility or profitability filters.

`reconciliation.summary` and `groups` preserve study-entry and admitted-watch denominators. `cases` provides entry identity, price references, quote timing, endpoint comparisons and `rebased` comparisons. Groups remain separate by cohort and sampling policy. Repeated exports must still be deduplicated by source identity and observer sequence.

## What it does not establish

The scanner's `marketObservedAt`, research history `at` and checkpoint `sampleAt` are local response clocks. The price adapter does not preserve an independently verified exchange price timestamp. A recent response or nearby receipt does not prove current or simultaneous market prices.

Token decimals are not verified in these exports. The audit does not guess them, turn atomic token quantities into whole tokens or calculate an absolute quoted token unit price. Quoted input/output arithmetic remains independently checked by the joined report. Quotes are not fills; fees, price impact, pool routing, provider cache effects and fast price changes can contribute to differences. The audit does not assign a cause or correct historic prices automatically.

Large differences persisting after rebasing cannot be attributed solely to the original entry reference. Small rebased differences also do not prove stale entry prices: observation timing and other execution differences remain possible. A reported provider error is not proof of permanent unsellability.

## Findings reproduced from the supplied six-hour report

- 911 entries match observer decisions; 34 watches were admitted. Original cohort returns and failure counts remain unchanged.
- At 30 seconds there are 32 valid sell quotes, but only 31 valid paired paper/quote observations. Of those pairs, 15 have opposite return signs and 13 differ by at least 20 percentage points. All 13 meet the close-receipt/original-pool/on-time diagnostic conditions.
- Rebasing at 30 seconds still leaves 16 of 31 pairs with a discrepancy of at least 20 percentage points at 60 seconds; 15 meet the strict timing and route conditions.
- The largest baseline endpoint discrepancy was paper −86.15% versus quote +5.45% at 30 seconds. From the 30-second reference to 60 seconds, the respective changes are +5.26% and +14.99%; from 30 to 120 seconds, +36.96% and +32.65%. Its initial price reference therefore merits investigation, without assuming it was wrong.
- Entry history is `not-exported` in all 911 cases in that older report. Observer receipt metadata is available for baseline/Fast30, while early-activity receipt metadata is absent there. New collector projection can expose already-retained research history without changing the observer or scanner.

## Implementation and validation

Collector `launch-study-1.0.2` adds an allowlisted projection of existing entry-history prices and receipt times. It retains the same indexed database queries, ten-second read budget, WAL/raw-byte/row limits and read-only transaction. At most 24 samples per entry are exported; source histories above 256 samples or malformed sample envelopes fail publication. Added projected evidence increases report size and offline CPU somewhat; the existing 64 MiB report ceiling still applies.

Eighteen added tests cover old exports, bounded allowlisting, read-only source preservation, reference mismatches, future/wrong-pool/contradictory timestamps, quote failures, missing anchors, unknown routes, late observations, rebasing arithmetic and recomputation. Existing joined-report tests continue to check quantities, publication, replay and wrapper cleanup. Actual report replay verifies the original `analysis` remains identical.

The next gate is a fresh host export confirming the added entry-history projection and inspection of flagged entry references. A scanner/provider change should follow a demonstrated defect or a precise missing-evidence requirement. Signal thresholds and prospective trading hypotheses remain frozen during this measurement investigation.
