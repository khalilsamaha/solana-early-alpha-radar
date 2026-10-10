# Roadmap to a limited real-money pilot

Status as of 5 October 2026. These are project decision gates, not a promise of profitable trading or a scheduled date to deploy capital.

| Stage | Status | Exit evidence |
|---|---|---|
| 1. Hosting and recovery | Operational in supplied checks | Healthy service, external down alerts, scheduled verified off-host backups and restore rehearsal; keep monitoring resource growth |
| 2. Measurement integrity | Improved; this release adds explanations | Preserve original pools, explicit missing evidence, real timing, separate immature records; investigate remaining provider/pool gaps |
| 3. Entry/exit edge | Current stage, not passed | A frozen rule survives later, deduplicated data, delay/cost stress, severe-loss review and comparison with excluded opportunities |
| 4. Execution dry run | Not implemented | Size-specific buy and sell quotes, observed latency, fees/impact, route failures, token restrictions, feasible unsigned simulation and position/capital constraints |
| 5. Limited manual pilot | Blocked on 3 and 4 | Explicit user-approved budget/position limits, separate wallet, manual signing, monitoring and a stop procedure |
| 6. Broader or automated use | Not approved | Real fill/fee/failure evidence from pilot, reproducible reconciliation and tested control mechanisms |

## Why we are not at the real-money gate yet

The 232-entry baseline backup had negative mean returns under all 27 tested policy/delay/cost scenarios. The primary three means were approximately -9.18%, -9.29% and -9.81%. These are model results, not realized wallet losses. The current evidence supports changing the research questions, not placing trades to find out whether the negative model was right.

Most severe modeled stop exits were already far below the stop threshold at first observation. We must distinguish actual collapses from provider anomalies and learn whether useful signals arrive before the move, while preserving failed and missing cases. A paper stop is not a loss cap.

## Next engineering work after this release

1. Recapture the completed backup and live database with 1.1.0. Use the new loss cases and entry feature availability to investigate recorded price/liquidity collapse patterns immediately.
2. Audit alternate-pool cases separately. Keep the original-pool outcome and token follow-up evidence; verify migration/route context before considering an executable cross-pool exit model.
3. Review the three frozen comparisons on future entries. Do not repeatedly optimize thresholds on the same past sample. If all remain negative, develop a distinct phase-specific entry hypothesis and assign a new experiment version. Existing filters are not the final trading strategy.
4. Build a quote-only execution monitor in parallel once its request budget and API availability have been checked. Quotes must cover both directions and a specified position size, not just token spot prices. No signing or submission is needed for quote observation.
5. Replay with measured latency/cost/failure assumptions and capital constraints. Only then review a real-money pilot.

## Proposed review gates

The following are working acceptance criteria for the project, not universal statistical guarantees. They are deliberately not implemented as an automatic capital-deployment switch.

- At least 95% of mature cases in the proposed selected cohort have usable evaluation evidence, with the remainder explicitly classified. Missing/failed exits remain visible in stress results. Pool migration must not hide a failure.
- First structured forward review after at least 200 distinct selected mints across at least three non-overlapping UTC dates. This is a minimum review sample, not proof of an edge; correlated episodes and uncertainty still require analysis. We can reject a clearly failing rule earlier.
- Positive average net result on later data, not merely a positive median; examine uncertainty, separate time blocks, and sensitivity to removal of the largest winner. A win found only at zero delay or zero cost is insufficient.
- The proposed rule remains credible under measured execution delay/cost assumptions and realistic failure handling. Current fixed 1%/3% assumptions are research stress tests and must eventually be replaced by measured size-specific evidence.
- Entry-time security/data checks and exit-route availability must be satisfied. Missing liquidity or security data is not evidence of safety.
- Dry-run output must reconcile decision time, notification time, quote time, route, quoted amount and intended size. Show available and failed buy/sell quotes; do not filter failures out of the assessment.

There is no calendar promise for stages 3 and 4: they can proceed in parallel, but a negative edge cannot be cured by waiting a fixed number of days. Reports every 30 minutes support immediate diagnosis; each update should answer a defined question.

## Pilot definition, when gates are met

A pilot would test execution and reconciliation first, not prove profitability. Before it starts, agree a total experiment-loss budget, maximum position size, maximum open exposure and trade count, and stop conditions. Use a separate limited wallet, manually approve transactions, verify mint addresses, and log actual fees/fills. Stop on unexpected permissions, inability to sell, stale signals, route/price discrepancies beyond the agreed tolerance, or the loss budget being reached. A total wallet budget can bound funded exposure; an individual stop cannot guarantee the exit price.

No wallet, budget or transaction authorization is requested by this release. We will make the proposed pilot concrete before asking for that decision.

## Execution reference

Jupiter's current Order & Execute documentation separates getting an order/quote, signing and executing. Omitting `taker` allows quote-only use. A returned quote is not proof of an assembled transaction or successful execution.

- https://developers.jup.ag/docs/swap/order-and-execute (checked 5 October 2026)
- https://developers.jup.ag/docs/swap/advanced/slippage (checked 5 October 2026)

These support the proposed quote-only stage; this package does not call those endpoints.
