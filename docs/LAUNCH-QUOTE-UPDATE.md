# Joined launch and quote report — 11 October 2026

This development automates the comparison between information available at a signal, the observer's admission decision, original-pool paper observations and walletless route quotes. It runs alongside production with bounded, read-only database reads. No installer, scanner rebuild, service restart, new quote request, notification, wallet or trading rule is introduced.

## Run on Kali

Fetch `feature/launch-quotes-20261011` in `~/apps/solana-radar-dev` and detach at the exact GitHub commit supplied with the release. Then run:

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/launch-study/run-joined.sh --hours 6
```

Upload the one `radar-launch-quotes-*.json.gz` file printed at completion. The script first reads the scanner's launch/research evidence, then exports the existing observer ledger using installed observer 0.6.0. It requests one extra hour of quote history to protect the start boundary between sequential reads. The matched analysis uses the overlapping window; the wider quote export is a separate comparison with a different denominator. Requested hours are 1–24. Actual launch coverage can be shorter after registration.

The scanner collector retains its 10-second read budget and existing source caps. Each decompressed input and the final report are capped at 64 MiB; joins accept at most 20,000 observer decisions and 1,000 probes. Reaching a cap fails without publishing a partial report. Try a shorter window instead of raising limits. Temporary files are private and removed on success or failure. The final file is published atomically with mode 0600 and never overwrites an earlier report. This command does not create a timer.

To join the two already supplied reports without touching the databases:

```bash
cd ~/apps/solana-early-alpha-radar
python3 ~/apps/solana-radar-dev/launch-study/joined_report.py \
  --study radar-launch-study-20261011T150338Z-2494639.json.gz \
  --quotes radar-auto-quotes-20261011T150701Z-2502364.json.gz \
  --output "radar-launch-quotes-replay-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

A joined report retains projected evidence and can itself be replayed:

```bash
python3 launch-study/joined_report.py \
  --input /path/to/joined-report.json.gz \
  --output /path/to/new-replayed-report.json.gz
```

Derived summaries are recomputed, not trusted. Input digests identify the decompressed inputs; they are not independent attestations of completeness.

## Join and timing rules

- Source database identity must match. Early-activity and Fast30 joins require exact entry ID, source sequence, cohort, mint, signal time, pool and price. Baseline research IDs differ from alert IDs: their joins instead require a unique cohort/mint/time/pool/price tuple and a valid alert identity. Level 2 can be the first baseline alert.
- Duplicate or ambiguous identities stop publication. Missing/mismatched decisions, skipped signals, absent probes and failed quotes remain explicit. They never receive zero or fabricated returns.
- Matched outcomes use the earlier report cutoff and the overlapping entry window. Paper outcomes are reanalysed at that cutoff; quotes received later cannot enter earlier results. Export-time probe state is labelled separately. Unstamped skips require completion evidence at the cutoff or remain unavailable.
- A valid buy quote is the recorded hypothetical 10 USDC input. Sells must reverse exactly the buy's atomic token quantity into USDC. Mint, amount, clock and stored-return checks precede arithmetic; Python integer quantities avoid loss of large-token precision. Other notionals do not mix into this experiment.
- Thirty seconds after the buy response is the primary descriptive quote comparison. Sixty and 120 seconds are comparators. The on-time summary excludes requests more than five seconds late or responses taking more than eight seconds. All valid quotes, including late ones, remain in a separate summary. Zero-offset sells are spacing-delayed, not instantaneous.
- Paper checkpoints use signal time; quote exits use buy-response time. Paired paper/quote statistics include all valid paired observations, including late quotes. Each case records the actual timestamp difference. Their return difference is not measured slippage.
- Original-pool membership is recomputed from reported route legs. Missing or truncated routes remain unknown even when amounts are valid. Route availability does not prove a fill, depth, safety or net profit.

`analysis.groups` preserves all matched-window study entries and admission/failure denominators by cohort and sampling policy. `analysis.launchContrasts` additionally separates follow-up admission/policy, liquidity stratum and trader/URI-hash group. `analysis.wholeQuoteExportGroups` preserves the wider quote-window results. `analysis.cases` contains the per-entry evidence and join states. Unmatched observer records, study entries outside the common window and unlinked probes are listed separately.

## Verification against supplied evidence

The two supplied 11 October exports reproduce 609 matched observer decisions and 27 admitted watches: eight baseline, ten early-activity and nine Fast30. All 27 have valid 30-second quotes. Mean quoted changes at that primary horizon are respectively −0.48%, −2.22% and −0.13%, before any additional execution/cost model.

The matched nine Fast30 watches average +30.01% at 120 seconds, but the wider supplied quote window has eleven Fast30 watches, averaging +14.30% with a −93.68% worst result. Both scopes remain visible. Neither a small positive subgroup nor a retrospectively attractive exit establishes an edge. Quote sampling is capacity-limited and non-random.

Twenty new tests cover three-cohort identity joins, initial level-2 baseline alerts, duplicate and mismatched records, fixed integer amounts, failures, future evidence, late responses, unknown routes, replay, private publication and wrapper cleanup on export failure. Real-file replay validates the joins and totals; the first fresh Kali run still needs confirmation.

## Next decision

We are evaluating launch features and execution evidence, before a frozen prospective strategy trial. Inspect usable group sizes, unknown fields, losses, timing and quote failures. If a feature merits testing, register one hypothesis and evaluation protocol before collecting its validation period. The present descriptive report does not change entry eligibility or select a winning exit. Execution controls and funded testing remain later stages with no justified start date.
