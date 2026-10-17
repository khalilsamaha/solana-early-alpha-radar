# Readiness and reconciliation release — 17 October 2026

This release adds diagnostics and a read-only chain evidence component. **No scanner rebuild, observer reinstall, service restart, new provider quota, model fitting, rule change or cloud transfer is needed.** The registered feature protocol and its hash remain unchanged.

## Evidence reviewed

The supplied 72-hour capture contains 11,563 raw signals and 395 watches. The existing validation rebuild yields 10,322 eligible signals and 166 compatible watches: 50 baseline, 59 early-activity and 57 Fast30, across two UTC days. All original readiness cohorts and guard results replay exactly under the new report.

| Cohort | Compatible watches | Returned on-time 30s quotes | Mean quoted change | Median quoted change |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 50 | 50 | −3.31% | −0.18% |
| Early activity | 59 | 55 | −5.93% | −3.74% |
| Fast30 | 57 | 55 | −2.25% | −4.20% |

These are descriptive changes in returned fixed-quantity quotes, not fills or net profit. Unavailable quotes remain in state denominators without invented returns. One Fast30 failure at 30 seconds recovered by 120 seconds; five other failed 30-second watches remained failed at 120 seconds. Baseline had a separate later failure. A provider failure is not permanent unsellability.

The return-target fit guards still need 50/45/45 additional labelled watches and a third distinct UTC day, respectively. Availability targets also lack failure-class examples (20/16/18 additional examples). These are minimum fitting safeguards, not evidence of an edge or a collection deadline. A return model and an availability model have separate gates; one must not manufacture labels to unblock the other.

## New tools

1. `forward-study/readiness_details.py`: validates and deduplicates original capture chunks; preserves the existing readiness output; adds per-cohort/day return distributions, all admitted denominators, tail losses, best-observation removal, failure/recovery transitions, entry-feature availability and ages, actual request timing and exact guard deficits. It neither registers nor fits anything. Timing/outcome fields remain outside model features. The first reverse request actually occurs roughly 9.7 seconds after the buy response in this capture, despite its nominal zero offset.
2. `chain-reader`: two-method bounded public RPC reader with finalized identity/balance reconciliation, plus offline synthetic self-check. Its report cannot authorize resubmission or update a ledger. Live RPC integration is not claimed from passing offline tests. Signing, simulation, expected swap-intent validation, expiry, account lifecycle handling and execution controls remain separate work.
3. `deployment/inventory.py`: compares the release's expected hashes with scanner host files, current container files and installed observer 0.9.0 files. Reports selected container/unit state and dev commit. Missing permissions remain unavailable. Container files and configured service versions do not prove every resident module's identity. The root import manifest is left as historical provenance.

The manifest lists only source files. The inventory never prints environment variables, Compose configuration, logs, credentials or database contents. Running it with `sudo` allows Docker and installed observer access; it makes no external requests and changes no services. A filesystem hash difference is a review item, not an instruction to overwrite the host.

## Host commands after checking out the pinned release

Use the pinned commit supplied with the release message in `~/apps/solana-radar-dev`. Keep production in `~/apps/solana-early-alpha-radar`.

Run the richer report on the capture already collected; no additional waiting or downloads:

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/forward-study/run-review.sh \
  "$PWD/radar-forward-check-20261017T094430Z-4024482/capture"
```

Record the installed source and container identity:

```bash
cd ~/apps/solana-early-alpha-radar
sudo python3 -E -s ~/apps/solana-radar-dev/deployment/inventory.py \
  --project "$PWD" \
  --output "$PWD/radar-deployment-inventory-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

Run the offline chain reader check:

```bash
cd ~/apps/solana-early-alpha-radar
python3 -E -s ~/apps/solana-radar-dev/chain-reader/run.py \
  --output "$PWD/radar-chain-self-check-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

Upload the three report paths printed by these commands. Reports use mode 0600, preserve the invoking user as owner when run through sudo, and refuse overwriting existing outputs.

## Next gates

Continue the current observation protocol. Fit only a cohort/target that independently passes the fixed guards, freeze its model, then evaluate later unseen-token evidence with the existing embargo and holdout requirements. Negative descriptive returns and incomplete availability evidence do not justify a funded pilot.

In parallel, finish transaction-intent reconciliation and test recovery against recorded/devnet transactions before building any separately authorized signer. An engineering smoke test and a profitable strategy are different milestones. No date or probability of earning money is established by this release.

Backblaze remains the chosen pay-as-you-go service. This release does not alter caps, retention or verification, and does not assert recovery of the previously failed cloud jobs.

## Release verification

634 automated tests passed locally: 612 source/regression tests and 22 offline ML/model tests. This includes 24 new tests for readiness detail, chain-reader edge cases/transport and source inventory. The uploaded 12-chunk capture replay preserved every original cohort/guard result and the registered protocol SHA-256 `65cf32c393a369a3b6fd01e768636e1696eb15abc533457825156db5490edbb8`. The local inventory matched all 52 scanner source files; host Docker/service results require the user-side commands above. Synthetic chain self-check passed without network requests.
