# Current-state reverse cost observation — 29 October 2026

This increment adds a fresh, unsigned reverse-direction observation to the existing
controlled devnet route. It does not reopen either completed cycle or activate a
sender. Use `position-book/reverse_cost_cli.py`; no scanner rebuild, service restart,
key access, journal mutation or new reservation is required.

Host checkpoint accepted October 29 at 18:59 UTC: 998 atomic input, 996 quoted/
simulated output, 5,000 lamport fee within the 10,000 cap, 7.671-second completion,
unchanged closed journals and zero sends/signatures. Public arithmetic/hash/clock
checks passed; raw RPC/journal replay was not included in the uploaded summary.
Next: [independent paired costs](PAIRED-COST-OBSERVATION.md).

## What is established

1. Revalidate the locally reconciled closed cycles and pinned deployed program.
2. Price a fresh reference entry from the current pool. Reverse exactly that
   quote's entire output, swapping source/destination, mints and vaults. Reject an
   output over the existing 1,000-atomic scope instead of truncating it.
3. Build a fresh unsigned reverse message; recapture pool, actual source account,
   native funds, blockhash and message fee. Pool economic inputs must match the
   original observation. Existing token funds after local reservations must cover
   the reverse input; hypothetical entry proceeds cannot supply them.
4. Run one unsigned reverse simulation. Revalidate its own pre/post token and
   native effects, fee, exact message and quantities, final cluster identity and
   locked local reservations. Original quote freshness remains ten seconds.
5. Report the reverse fee cap and a separate known-cap subtotal: declared entry
   cap plus validated reverse cap, with priority included once. Show any current
   native shortfall. Unknown entry fee and failed-attempt budgets remain null;
   `roundTripFundingEstablished` and execution approval remain false.

There are at most 20 public devnet requests, including one simulation, no retries,
and a 30-second request-start budget. A timeout, changed pool, deployment drift,
STOP marker, insufficient funds or missing evidence yields `unavailable`.
Preserve and upload that report; do not change caps or journals to force a pass.

## What is not established

Both quotes use the **same observed pre-entry pool**. The entry is not executed or
simulated; its token affordability and message fee are not verified. Existing inventory funds the reverse
simulation. Its successful result is not a post-entry exit or a measured round trip.
No quoted round-trip return or net profit is calculated. A funded subtotal is not a
complete funding plan. Native valuation, complete paired-leg fees and failed-attempt
budgets remain separate work. Matching sampled effects is not proof of source and
deployed-code equivalence or arbitrary-route safety.

This command is restricted to the existing devnet setup and standard SPL accounts.
The explicit October 27 deployment observation applies only to unsigned simulation;
legacy sender pins are unchanged. The frozen model and production sampling are unchanged.

## Kali checks

After checking out the published release commit, run:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
radar_cli="$HOME/apps/solana-radar-dev/position-book/reverse_cost_cli.py"
python3 -E -s "$radar_cli" \
  --output "$PWD/radar-reverse-cost-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
python3 -E -s "$radar_cli" \
  --simulate-devnet --deployment-observation-20261027 \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-reverse-cost-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

Expected offline state: `offline-checks-passed`, ten cases. Desired host state:
`controlled-reverse-cost-observation-consistent`. Upload both public reports,
including an unavailable observation. Never upload private journals or keys.

## Local validation and next boundary

The new tests exercise real collectors and parsers over fake HTTP: exact reverse
quantity and wire, actual token shortfall, token/native reservations, pool and
blockhash drift, malformed simulation, original quote expiration, final ledger
change, STOP and output overwrite protection. Existing entry observation paths
are covered by their regressions.

Local validation passed: the 160-test position/accounting regression run, 169
quote/preflight/rehearsal/setup dependency tests, and the final ten-test reverse
suite (rerun after the last report-label changes; overlaps the regression run).
The CLI also passes its ten deterministic offline cases. Source hygiene and
whitespace checks pass. No live RPC or host test has been run by this release.

After the host observation is reviewed, build the paired-entry/exit cost contract
with explicit post-entry state provenance and failure budgets. Do not infer paired
round-trip results by multiplying the two independent current-state quotes.

## Separate confirmation study

The supplied October 29 public registration matches the pinned protocol, model,
source identity and window rules. It records 1,186 excluded development tokens.
The private registration digest cannot be independently reconstructed from the
public summary alone. Observation starts October 30 00:00 UTC and ends November 6
00:00 UTC; review opens November 6 00:05 UTC (01:05 Amsterdam). No refit or admission
change is allowed. Preserve captures November 1, 3, 5 and 6 using the existing
`availability-study/preserve.sh`; no timer is installed by this increment.
