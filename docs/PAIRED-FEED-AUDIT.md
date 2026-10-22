# Paired feed audit — 12 October 2026

## Findings from the uploaded six-hour report

Input: `radar-launch-quotes-20261012T111146Z-956384.json.gz`. Window: 07:11:58–13:11:58 Europe/Amsterdam on 12 October 2026. The source read took 0.823 seconds. All 752 entries have valid feed timing and matching entry-history prices. Of 2,990 outcome records, 2,925 carry valid timing; unavailable observations are not supplied with invented timing.

There are 33 admitted watches, with no overlap with the previous 06:43 export's six admissions. At 30 seconds, 30 watches have paired usable paper/quote observations. Sixteen pairs have opposite return signs; fifteen differ by at least 20 percentage points. Eleven also have close receipts (within five seconds), timely quotes and the original pool reported on both buy and sell routes.

The new audit matches transport records to those exact entries/checkpoints:

| Evidence among the 11 large, close-receipt, original-pool 30s disagreements | Count |
| --- | ---: |
| Both local queue-to-application durations below one second | 11 |
| Both responses report cache MISS | 8 |
| A response reports positive HTTP Age | 3 |
| Paper/quote receipts within one second | 8 |
| Both reported token-touching route pool sets contain only the original pool | 11 |

The three positive-age checkpoint records report 12, 16 and 24 seconds, all from the pinned-pair endpoint. This is HTTP cache evidence, not an independently verified price timestamp. Cache MISS does not rule out upstream aggregation or caching. Sub-second local timings do not establish simultaneous market state, nor exclude price impact, route costs, source conventions or buy-entry timing differences. We have evidence against slow local handling as a complete explanation, not proof of a particular upstream defect.

At 60 seconds, thirteen large discrepancies pass the same close-receipt/original-pool/on-time criteria. All thirteen have sub-second local pipelines; eleven report cache MISS on both measurements. Only one has receipts within one second. At 120 seconds, none pass the five-second receipt proximity criterion; those observations must not be described as tightly aligned.

## Quote observations, with failures retained

These are gross quoted changes for fixed hypothetical token quantities, not fills or net profit.

| Cohort | Admitted | Valid 30s quotes | Mean 30s quoted change | Mean 120s quoted change |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 9 | 8 | -8.00% | -0.65% |
| Early activity | 12 | 10 | +15.51% | -14.06% |
| Fast30 shadow | 12 | 12 | +8.66% | -7.27% |

One baseline buy quote failed. Two early-activity watches received buy quotes but all four sell-quote attempts failed with quote-generation-failure reports. Their unknown returns are not zero and are not dropped from admission denominators. Removing the best observed 30s watch reduces the early-activity mean to +2.99% and Fast30 to +2.68%. Small, nonrandom samples and previous negative windows remain relevant; no strategy was promoted.

## Development delivered

`paired-feed-audit-1` extends the existing joined report. It joins immutable source entry/checkpoint records to freshly validated reconciliation cases, including special baseline IDs. Each admitted watch has explicit records at 30, 60 and 120 seconds with:

- Price, pool and receipt binding checks before a timing record can be used.
- Request queue/body/application clocks and the interval from application to recorded event.
- Signal-to-buy request/response clocks, paired receipt differences and unchanged quoted/paper returns.
- Separate cache MISS, positive HTTP Age, HIT without positive Age, and unknown categories.
- Original-only token-touching pools, original-plus-other token pools, absent original pool, and unavailable/truncated routes.
- Missing, pending, gapped, invalid, unquoted and failed-quote states retained explicitly.
- Summary denominators by horizon, cohort, sampling policy, endpoint and cache category.

The API route may still contain conversion legs even when the token touches only its original pool. Repeated horizons and shared HTTP requests are not independent samples. Diagnostic thresholds are not new signal eligibility filters.

This is an offline reporting update. No scanner rebuild, restart, configuration change, new API request, notification, trade or Backblaze change is required. Existing collectors continue running. Previous analysis, reconciliation and aggregate feed timing replay identically.

## Use

Fetch the tested branch/commit from the accompanying instructions into `~/apps/solana-radar-dev`. Future exports use the same command:

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/launch-study/run-joined.sh --hours 6
```

The attached report has already been analyzed. There is no need to recollect it. To reproduce the new audit locally using the existing file and no database or provider access:

```bash
cd ~/apps/solana-early-alpha-radar
python3 -E -s ~/apps/solana-radar-dev/launch-study/joined_report.py \
  --input radar-launch-quotes-20261012T111146Z-956384.json.gz \
  --output radar-paired-feed-review-20261012.json.gz
```

Output contains the original source evidence and new `pairedFeedAudit` object. Publication is private and atomic, and refuses to overwrite an existing output file. Returning to the preceding development commit restores the old report behavior; production is unchanged.

## Next engineering decision

Do not respond to these discrepancies by increasing polling or lowering alert thresholds. First separate the original-pool provider measurement from route and entry/exit timing effects using the retained case evidence. The next data-source experiment should have a fixed per-request budget, explicitly bound pools and timestamps, and a prospective comparison protocol. A cache-only fix cannot address the eight close 30s discrepancies with both responses reporting MISS. Faster scanner CPU alone is also unsupported as the remedy.

Keep primary execution research quote-based, retain all quote failures, and evaluate the already-declared 30/60/120-second horizons across independent windows. Do not select an exit rule retrospectively from this six-hour window. Funded testing remains gated by credible prospective results and separate execution controls.
