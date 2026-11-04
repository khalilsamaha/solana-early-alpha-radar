# Preserved exit observation — 4 November 2026

The Kali encoding profile passed all 12 connected integration and 10 signer checks.
Connected offline elapsed time decreased from 6,786.773 to 5,236.220 ms (22.8%)
in one before/after host pair. This establishes a useful diagnostic improvement,
not proof that live execution fits the ten-second collection deadline.

The actual devnet position remains `exit-prepared`. Its original preparation and
one consumed replacement are expired; acquired inventory and unused fees remain
held. Neither a second replacement nor another execution is authorized by this
change.

## New diagnostic

`position-book/preserved_exit_observation_cli.py` defaults to disposable offline
checks. Its only operational action, `observe`, requires explicit devnet observation
opt-in, wallet, pool, private directory and both exact preparation hashes.

The collector holds the existing source lock and a read-only SQLite admission
snapshot. Before RPC and again after collection it replays both preparations,
checks their lineage and expiration, and rejects later signing/transport evidence,
backend markers (including dangling symlinks), STOP and unknown admission tables.
It collects at most twenty fixed devnet requests, including unsigned simulation,
with no retry. The existing original ten-second freshness budget remains intact.

Fresh evidence receives the existing full pool/account/quote/simulation review and
raw provenance review. An in-memory relationship check verifies unchanged acquired
quantity, protected inventory, remaining fee commitment, new blockhash and
non-regressing slot against the current saved replacement. No preparation is
appended. The SQLite snapshot closes without writes; there is no signing, sending,
fee-hold release, scanner deployment or study modification.

## Reading the report

- `preserved-exit-observation-complete`: all observation checks passed within the
  original collection deadline.
- `preserved-exit-observation-unavailable`: an identity, state, provider, freshness
  or validation check failed. Request count, stage and sanitized diagnostic remain
  available. No execution retry follows either result.
- `observationTiming` records collection elapsed time and remaining deadline
  headroom at collection and after full validation, when those stages complete.
  Missing values mean the stage did not complete, never zero latency.
- `persistenceAndSigningHeadroomMs` remains null. The diagnostic performs neither
  persistence nor signing/sending; its remaining time is not an execution permit.
- Public reports contain hashes and summarized bindings, not unsigned wire bytes,
  raw provider replies or private keys. Existing private journals remain local.

Run the offline check first, then one explicitly scoped observation on Kali. Upload
only those public `.json.gz` reports. No Docker rebuild or service restart is needed.
If the observation fails, preserve the report and journals and inspect the recorded
stage; do not run the existing execution command as a retry.

## Next decision

Use the host result to separate provider/collection delay from local replay cost.
A later reviewed continuation must preserve all generations, ownership, cumulative
holds, deadline checks and one-send recovery. That continuation is not implemented
or authorized by this diagnostic. Frozen study and availability capture schedules
remain unchanged; engineering success is not evidence of profitable trading.

## Local verification

The portable matrix passes 24 cases, including exact-identity rejection, original
and replacement byte preservation, consumed-slot refusal, concurrent SQLite commit
blocking, STOP, backend markers, later signing evidence, schema/lineage changes,
provider failure, expiry, clock regression and full provenance revalidation. Four
additional CLI boundary tests pass; existing collector (5) and unsigned replacement
(7) test modules remain green. Partition coverage (2), tracked source hygiene and
public deadline consistency also pass. Host live evidence is still pending.
