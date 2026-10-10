# Frozen shadow comparisons: entry-screen-1

Purpose: measure whether a small set of existing, entry-time conditions separates severe losses from useful opportunities. They are hypotheses, not claims of an edge. They do not wait for a new entry, alter notification eligibility, or detect a new kind of opportunity.

| Rule | Selected | Excluded | Unknown |
|---|---|---|---|
| history-ready-v1 | Entry qualification historyReady=true | historyReady=false | Not recorded |
| known-liquidity-5000-v1 | Entry liquidity >= $5,000 | Known nonnegative liquidity < $5,000 | Missing/invalid liquidity |
| qualified-liquidity-5000-v1 | Entry liquidity >= $5,000 AND existing qualification retain | Either known condition fails | Otherwise insufficient evidence |

The $5,000 boundary is already used in scanner research; it was not selected by searching these reports for the best threshold. The existing qualification's retain states are rising activity or recovery observed. The previous sample did not demonstrate that this qualification improves baseline returns. This comparison tests it rather than presuming that it works.

Each rule is evaluated separately within baseline and early-activity cohorts, with selected/excluded/unknown groups all reported. All three fixed exit policies are checked at 10-second entry delay/1% cost per side, 30-second delay/1% cost, and 10-second delay/3% cost. Exits keep the same 10-second response delay. Group summaries include unresolved/pending counts, severe losses, positive outcomes, median, mean, extremes, mean excluding the best winner and the explicit unresolved-as-total-loss stress scenario.

The installer saves the rule definitions' hash and first registration timestamp in `/var/lib/solana-radar-research/shadow-registration-v1.json`. Entry timestamps on or after registration are labelled prospective; earlier entries are exploratory. Reinstall preserves registration. A different registered rule hash is refused. Rule changes require a new version and registration, not rewriting the same hypothesis after seeing winners.

The source file is also fingerprinted in every analysis result, and the evaluator has its own fingerprint. Review fingerprints when combining reports. Prospective timing is not itself proof of independence or profitability.

Do not aggregate rolling report totals. Deduplicate by entryId, rule and policy scenario, retain the latest eligible evidence, and document every update to an earlier unresolved outcome. The current report does not merge files automatically. Baseline and early-activity can contain the same mint.

Missing-feature entries are not silently removed; they belong to unknown. Future liquidity/metadata is never substituted into entry-time features. Stored metadata may be stale: available original timestamps are exported, but absence of timestamps does not establish freshness. Security descriptions reflect limited recorded checks, not a guarantee of tradability or safety.

A rejected winner counts as a missed existing opportunity; the report cannot count tokens the scanner never discovered. Broader launch discovery and newly timed momentum entries require separate instrumentation and experiments.
