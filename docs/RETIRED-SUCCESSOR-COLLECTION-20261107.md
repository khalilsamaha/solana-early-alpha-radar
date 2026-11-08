# Bounded successor collection — 7 November 2026

The Kali unsigned-successor report passed 12/12 cases at 17:57:42 UTC on November 7. It exercised disposable synthetic journals only. This increment connects a fixed raw collector and exposes a read-only observation command, while live durable preparation and signing remain separate gates.

## Behavior

The command fully replays the existing position and exact retirement under the existing source lock and a read-only SQLite snapshot. It checks the original policy budget before network work. Eight fixed devnet requests recheck the expired signature, transaction absence, block height and five scoped accounts. A conflict prevents any quote requests.

It then uses the existing twenty-request quote/simulation pipeline, including the fixed-endpoint HTTPS session, raw account validation, message fee and simulation checks. Source and retirement guards remain enforced. The original ten-second collection freshness is unchanged; the total operation budget is 120 seconds and the expiry/account phase budget is at most 30 seconds. Each network timeout is clipped to the remaining operation budget. STOP and operation budget checks run before every request. Failed requests are not retried.

After collection, the accepted successor contract recomputes the exact binding: retirement and old preparation identities, distinct blockhash, attempt two, owned quantity, protected inventory and original held fees. Backend acknowledgment files are reread. Validation and snapshot-close time count against the original deadline; close errors clear any provisional success. The public report includes request counts, collection/validation timing and final headroom, but no raw transaction or provider body.

The source snapshot prevents concurrent commits while evidence is collected. It cannot prevent unrelated on-chain wallet activity. Every account mismatch remains a blocker; absence of a provider receipt is not proof of global non-execution.

Observation creates no candidate record, allocation, signature or transaction. It cannot be imported as signing authority. The same producer is exercised against the atomic successor contract in disposable offline tests; there is no live preparation action in this CLI.

## Kali acceptance

Use the pinned published feature commit. First run:

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/position-book/retired_successor_collection_cli.py" \
  --output "$PWD/radar-successor-collection-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Only after its offline checks pass, run one observation from the production project directory:

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/position-book/retired_successor_collection_cli.py" \
  --action observe \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --preparation-sha256 d8ab974e819a953ecf015aa3acee403e8ca30f822bac72e58d92263218f9dd97 \
  --retirement-sha256 58187fb8325ad175689182221481a802277b8e2ae89485a69d15697f7517015f \
  --output "$PWD/radar-successor-observation-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected success: `successor-observation-consistent-held`, 28 requests and positive final deadline headroom. A refusal is an actionable diagnostic; preserve the report and all journals rather than retrying automatically. Positive observation headroom does not yet include durable commit, independent signing or sending.

Upload both public reports. No Docker rebuild, scanner restart, key access or devnet submission is required. Scanner/quote-observer policies and research windows remain unchanged. The next integration must measure complete signing and send headroom without relaxing this deadline.

## Validation

The release self-check passed 13 connected/fault cases with network connections disabled. The shared pipeline passed five original capture tests. A further 38 collection, preserved-observation, replacement, continuation and HTTPS-session regressions passed with ResourceWarning treated as an error. Five command scope/output checks, two partition checks and source/package-manifest hygiene also passed. Real devnet timing on Kali remains the next acceptance step; no host observation has been claimed by these synthetic results.
