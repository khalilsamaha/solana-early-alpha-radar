# Fixed exit-availability confirmation — October 29, 2026

This is a separate prospective study of the **existing early-activity legacy
exit-availability model**, at its existing 0.5 threshold. It does not fit a model,
change admissions, add market requests, alter notifications or enable a sender.

## Why this study

The October 29 diagnostic successfully replayed the completed October 22–28
review. Its report hash, original model identity, five capture identities, group
counts and fixed-threshold partitions match the reviewed evidence. This is an
internal consistency check, not independent proof of provider accuracy.

In the completed early-activity cohort, the fixed legacy availability filter
excluded 20 of 63 provider-reported 30-second quote failures and retained all
218 returned quotes. It still retained 43 failures. Returned quotes averaged
negative returns; reducing quote failures does not establish a profitable trade.

The diagnostic also found the following retrospective differences:

| Early-activity entry feature | Returned quotes (218) | Provider failures (63) |
| --- | ---: | ---: |
| Median average reported trade size | $46.88 | $5.57 |
| Median reported holder count among known values | 26 | 4 |
| Known liquidity | 31 | 0 |
| Missing 30-second return feature | 47 | 48 |

These are associations, not causal explanations or newly chosen thresholds.
Unknown liquidity was also common among successes, so treating it alone as an
exclusion would discard many returned quotes. Holder count is not part of the
frozen legacy model tested here. The unchanged legacy inputs are return30sPct,
return60sPct, lastIntervalReturnPct and averageReportedTradeUsd.

Full training-distribution reconstruction was appropriately withheld: preserved
captures contained 116/119 baseline, 103/107 early return, 136/140 early
availability, and 130/133 Fast30 training rows, with nonmatching training IDs.
This does not invalidate the replay of fixed weights on forward entries, but it
limits training-distribution comparisons. The original model and captures remain
intact. There is no claim that richer features failed for one proven reason.

## Frozen design

The protocol is in `protocol.json`, stored verbatim and hashed in a new private
registration. It preserves the original model artifact and identifies the exact
legacy weights. The fixed model was selected using the completed study; this new
interval is its confirmation set, not an extension of the old holdout.

- Start: next UTC midnight strictly after registration plus five minutes.
- End: seven complete UTC days after start; signal interval is `[start,end)`.
- Review: no predictions or outcomes are returned before end plus five minutes.
- Population: compatible admitted early-activity watches under the original
  three-cohort sampling policy. No admission policy is changed.
- Token exclusions: original training tokens plus all admitted tokens in the
  accepted development captures. Retain only the first compatible admitted
  entry per new token. This does not mean every token ever observed is excluded.
- Primary measure: proportion of provider-reported 30s quote failures excluded.
- Paired safety measure: proportion of successful on-time 30s quotes retained.
- Separate economics: all/selected/excluded 30s and 120s quoted outcomes,
  unknowns, severe losses, illustrative extra cost stress and best-token/day
  removal. Failed quotes are neither invented losses nor zero returns.
- Probability comparison: frozen legacy versus original training-rate constant;
  no new fit, context competitor, feature selection or threshold search.
- Evidence guards: 200 known labels, seven labelled UTC dates, 20 provider
  failures and 20 excluded known labels; complete requested query coverage and
  a sufficiently late evidence cutoff. These are pragmatic review guards, not
  a statistical-power calculation or a profitability threshold.
- Results stay research-only even when all guards pass. A sparse result remains
  inconclusive; no automatic extension, reset, early stopping or promotion.

Wilson intervals are descriptive under an independence assumption. Market/day
dependence and the nonrandom quote sample limit interpretation; day-block Brier
intervals are also shown. No claim applies to unquoted or skipped signals.

## Register on Kali

Use the reviewed development commit and existing research virtual environment.
Run from `~/apps/solana-early-alpha-radar`:

```bash
bash "$HOME/apps/solana-radar-dev/availability-study/register.sh" \
  "$PWD/radar-frozen-forward-20261028T162813Z-1068720.json.gz" \
  "$PWD/radar-frozen-diagnostic-20261029T035656Z-2563125.json.gz"
```

Upload the printed public registration report. The new private directory is
`~/solana-radar-availability-study-20261029`. Keep it and the original experiment.
This step repeats the accepted replay before registering; it reads no live
database and makes no network requests. The accepted report identities are fixed
in source. Repeating registration returns the original dates, never a new start.
An incomplete installation stops and is preserved for inspection.

If registered on October 29 sufficiently before midnight UTC, the interval is
October 30 00:00 UTC to November 6 00:00 UTC (01:00 Amsterdam). Review opens
November 6 00:05 UTC (01:05 Amsterdam); reviewing later that morning is fine.
The registration report is authoritative if installed later.

## Preserve evidence, without looking at results

On the dates printed by registration (normally November 1, 3, 5 and the final
November 6 capture), run the following. Daytime on those dates is fine. Do not
allow more than 72 hours between captures; missed data may already be pruned.

```bash
cd "$HOME/apps/solana-early-alpha-radar"
bash "$HOME/apps/solana-radar-dev/availability-study/preserve.sh"
```

This uses the existing bounded read-only ledger exporter via sudo. It writes
private capture files in the new study directory, without evaluating models,
requesting market data, transferring from Backblaze or changing services.
There is **no new automatic timer** in this increment. Preserve every capture.
The final helper limits the entry-window end to the fixed review boundary,
including the existing 15-second maximum signal-admission delay. The capture
keeps later outcome receipts; the analysis still uses the original signal window.

Existing limits remain: eight captures, 512 MiB total decoded merge input,
100,000 source signals and 5,000 watches. A limit stops the command rather than
silently discarding evidence. Do not repeatedly capture the same window.

## Final review

After the printed review time, preserve the final capture first, then:

```bash
cd "$HOME/apps/solana-early-alpha-radar"
bash "$HOME/apps/solana-radar-dev/availability-study/review.sh"
```

Upload the review report. A request before the fixed boundary stops before
reading captures or computing predictions. Missing query coverage, sparse
failures or insufficient labels remain explicit. Capture coverage cannot prove
continuous uptime or recover records already pruned. Repeating the review does
not create an independent experiment; retain and report every result.

## Engineering continues during collection

Next engineering work is fresh exit-leg evidence and round-trip cost/funding
assessment, followed by mainnet-specific route/message validation. Keep the
completed controlled devnet cycles closed. A real-money mechanics test requires
its own agreed scope and execution guards; a strategy pilot additionally needs
credible prospective economic evidence. Neither is enabled by this study.
