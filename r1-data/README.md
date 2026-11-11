# R1 capture, transport controller and source feasibility probes

The capture core is Kali-accepted at `f92e4d1`; the offline subscription controller
and source metadata probe are Kali-accepted at `55ddf7a`; the bounded public RPC
probe is Kali-accepted at `d880134`; the event inspector is Kali-accepted at
`b28c8ff`; the documented schema comparator is Kali-accepted at `5d64039`;
native-SOL accounting is Kali-accepted at `27f812c`; deployment metadata is
Kali-accepted at `7fe6493`; finalized block positions are Kali-accepted at
`4d46229`; the capture handoff is Kali-accepted at `be8fcfe` and the synthetic
B2 round trip at `904a805`, both independently replayed from uploaded packages.
The provider wire is Kali-accepted at `a2fdf580` for its offline scope.
The offline supervisor is Kali-accepted at `1e8bed1a` and local measurement at
`ccf80858`. Complete-session handoff is Kali-accepted at `324a32e4` and its
uploaded archive independently restored. The current increment adds one fixed-
input B2 round trip for that exact complete synthetic session. It has **no live collector launcher, credential-file reader,
trading operation, profitability evaluator or curve reconstruction**. Its factory
opens a fixed provider connection only when explicitly invoked; no provider
connection is opened by the acceptance runner. Public RPC/B2 CLIs remain separate.
No change to the production scanner, frozen studies, E0 or CI is required.

## Kali acceptance

From a pinned isolated checkout, install the exact portable dependency in a new
virtual environment, then run the offline suite:

```sh
python3 -m venv .venv
.venv/bin/python -m pip --isolated --disable-pip-version-check install \
  --no-deps --only-binary=:all: --require-hashes -r r1-data/requirements-wire.txt
```

Dependency installation fetches one pinned wheel from PyPI's file service. It
does not contact PumpPortal. Then:

```sh
.venv/bin/python -E -s -B -W error::ResourceWarning r1-data/check.py --output /absolute/new/report.json
```

The wire requires exactly websockets 17.4, with a hash-pinned portable wheel.
Linux/Python 3.11+ and venv support are required (flock,
private POSIX files and SQLite). The report must be a new path in an existing
directory. The runner executes all `test_*.py` checks and then a synthetic
capture/restart/budget-stop/export/restore/replay exercise. Tests use private
temporary directories and remove them afterwards. No scanner database, existing
capture, environment credential or wallet is read. Report contents include code
hashes and runtime versions, not raw provider payloads or credentials.

Expected status: `offline-session-backup-passed-live-blocked`, zero failed/errored/skipped
tests, `local_restore_replay_passed: true`. This is not acceptance of feed quality,
an off-machine backup, reconstruction, billing, profitability or the full R1 gate.
Use `.venv/bin/python -E -s -B -W error::ResourceWarning -m unittest discover -s r1-data -v`
for detailed local synthetic-test diagnostics if the runner stops.

The current suite contains 287 tests. Earlier 44-test, 72-test, 101-test, 126-test, 137-test, 152-test, 167-test, 181-test, 198-test, 210-test, 227-test, 241-test, 259-test and 275-test Kali reports
remain accepted for their original pinned sources; they do not validate this addition.

## Complete-session B2 round trip (current Kali step)

First run the **287-test offline runner**, which pins 39 source files. No
`--session-artifacts` option is needed: reuse the exact **existing** accepted
27,148-byte session and its original 275-test receipt. Then explicitly run:

```sh
sudo -v
.venv/bin/python -E -s -B -W error::ResourceWarning r1-data/session_backup.py \
  --bundle /absolute/existing/session.zip \
  --acceptance-report /absolute/existing/275-test-report.json \
  --output-directory /absolute/new/session-roundtrip \
  --round-trip-b2
```

Only the accepted archive and report hashes are allowed. Local capture/journal
replay precedes any backup credential access. The fixed runner performs backend
verification, one upload and one download using the existing B2 configuration,
a separate random `session-` object in the R1 rehearsal prefix and the same
bounded command limits. It never retries, deletes, syncs or changes schedules.

Expected remote result: `synthetic-session-backup-passed-live-blocked`, with
both downloaded components replayed. Upload the offline report, the new
`report.json` and `downloaded.zip` when present. If the result is unavailable,
upload the diagnostic once without retrying. Exit zero means a report was
retained, not necessarily a pass. Retain the local evidence and remote object.

This validates one synthetic complete-session round trip, not actual live
capture retention or paid-feed activation. Existing B2 storage/API accounting
can apply. See `docs/R1-SESSION-BACKUP-20261111.md`.

## Complete-session handoff (Kali and independent replay accepted)

The following records the completed 275-test handoff. Do not regenerate its
archive for the fixed-input backup check above.

Run `check.py` with its usual new `--output` path and additionally
`--session-artifacts /absolute/new/directory`. This retains a fixed synthetic
capture/journal run and writes `session.zip` at that directory's root. Existing
artifact directories are refused. Without this option the runner still removes
its own temporary synthetic fixtures.

Upload **two files**: the **275-test offline report** (37 source hashes) and the
new directory's **session.zip**. The report includes
`supervision.worker_receipt.session_bundle_sha256`, `session_bundle_bytes`
and `complete_session_replayed: true`. Keep the retained directory on Kali.
Independent review will restore the uploaded archive using the report's trusted
checksum and compare both capture and measurement replay results.

The outer ZIP contains exactly `capture.zip`, `session.jsonl` and `binding.json`.
The original capture-only ZIP format and fixed B2 probe are unchanged. This
complete bundle is not yet covered by the earlier cloud receipt or a live
retention policy. The worker's per-file limit increases from 36 to 44 MiB to
fit the bounded combined archive; capture/journal and other process limits
remain unchanged. See `docs/R1-SESSION-BUNDLE-20261111.md`.

No key, funding, provider connection, sudo, cloud repeat or scanner restart is
needed. The generated transferable artifact contains synthetic data only.

## Local measurement evidence (offline scope accepted on Kali)

The accepted **259-test offline runner report** pins 35 source files.
The supervised worker now records an exclusive, bounded `session.jsonl` sidecar:
selected-creation receive timestamps, durable send intents, local completions,
abandoned commands and terminal state. Replay binds it to verified capture rows.
Delay uses monotonic time from local receive return to local send return; this
does not measure provider acknowledgement or the first complete trade stream.

The controller rechecks the capture deadline after flushing each intent. A
logging failure stops the session; selected-but-unsent creations and unresolved
sends remain explicit. Provider acknowledgement, external creation denominator,
initial-trade coverage and actual billing remain unknown. The report exposes
these fields under `supervision.worker_receipt.measurement`.

The journal is copied and replayed with the restored capture; expected
`measurement_restore_replayed: true`. The original two-member capture ZIP does
not embed the sidecar, so future off-machine coverage must preserve both files
and their binding receipt. No new cloud probe or live connection is requested.
See `docs/R1-MEASUREMENT-20261111.md` for the definitions and remaining critical
path. This continues the same R1 phase and its original effort cap.

## Process supervision (offline scope accepted on Kali)

The accepted **241-test offline runner report** pins 33 source files and records
`supervision`, including a reaped worker and a source-preserving capture/export/
restore receipt. The supervisor starts one fixed synthetic worker with a minimal
environment, Linux resource caps, a child wall alarm, parent-death termination,
a parent wall deadline and bounded TERM/KILL cleanup. Child output is discarded.
It has no live mode, credential input or arbitrary-command CLI. A private owner
folder lock coordinates cooperating runs in that same folder only; it does not
coordinate the production scanner or authorize provider coexistence.

Failures retain any run artifacts and cannot report acceptance. An unclean
capture is not automatically repaired or resumed. The check runner removes its
own temporary synthetic artifacts and records that removal explicitly. The
standalone `supervisor.py --owner-directory /existing/private/directory --rehearse`
interface retains a new run directory, but **no separate rehearsal is needed**
for this Kali step. The single check report suffices.

See `docs/R1-SUPERVISOR-20261111.md` for the tested limits, evidence acceptance,
remaining live-launch work and unchanged five-working-day effort cap.

## Provider wire (offline scope accepted on Kali)

The accepted **227-test offline runner report** records the required dependency,
30 source hashes, DNS/Internet-socket blocking and an in-memory protocol peer.
The tests execute real WebSocket handshake/framing code with simulated byte
transport. They do not dial a socket, conduct a TLS handshake, read a funded key,
subscribe to a provider or test actual provider availability.

The library fixes the PumpPortal WSS endpoint, validates TLS context settings,
disables redirects/proxies/compression and suppresses connection logging. It
allows only creation/migration and selected-token trade subscription operations.
One factory makes one connection attempt, with no automatic retry. It bounds
messages at 64 KiB and 64 fragments, limits completion after the first fragment
to two seconds, and preserves a single receive task across polling timeouts.
Abort/close stop receiving; disconnects remain gaps in the capture record.
These controls are not a provider billing guarantee or machine-wide ownership lock.

The connection decision is conservative: **one provider connection by default**.
Do not start the new wire beside the existing scanner. Live activation requires
either validated shared-connection integration or explicit provider confirmation
permitting the exact coexistence arrangement, plus an accepted launcher, host
TLS/session evidence, preservation coverage and the owner's numeric funding
approval. No live CLI is supplied in this increment. See
`docs/R1-PROVIDER-WIRE-20261111.md` for the dependency, tests and next decision.

## Synthetic B2 round trip (Kali accepted)

The uploaded 210-test result and downloaded package passed review and independent
restore. Do not repeat the cloud round trip; the following documents that step.

After the **210-test** offline runner passes, use the existing accepted handoff
package and its top-level rehearsal report. No new rehearsal is required:

```sh
sudo -v
python3 -E -s -B -W error::ResourceWarning r1-data/backup_roundtrip.py \
  --bundle /absolute/existing/handoff-run/export/capture.zip \
  --handoff-report /absolute/existing/handoff-run/report.json \
  --output-directory /absolute/new/backup-roundtrip \
  --round-trip-b2
```

This command uploads the **specific accepted 21,328-byte synthetic package** and
reads it back under a new random object name in the existing bucket's separate
`r1-rehearsal/` prefix. The fixed expected package and report digests prevent
substitution of real production data. It first performs a local restore, then
checks `radar-b2` is configured as B2. It invokes at most three subprocesses:
backend metadata, one upload and one download. No cloud list/sync/delete,
retention change, scanner restart or new paid feed is performed. Ordinary B2
storage/API accounting can still apply; this does not claim zero billing.

Python stays under the current user. `sudo -v` lets the existing rclone process
read `/etc/solana-radar/rclone.conf`; Python never reads or prints that config.
Upload bytes travel on stdin and download bytes on stdout, so privileged rclone
receives no user-controlled local file path. Each invocation has a root-owned
40-second timeout plus a two-second forced-kill window. Raw errors are discarded;
failed or uncertain uploads are not retried or deleted. Keep any resulting object.

Expected: `synthetic-backup-roundtrip-passed-live-blocked`, with both
`remote_download_verified` and `downloaded_capture_replayed` true. Upload the
210-test offline report, new `report.json` and `downloaded.zip` when present.
`synthetic-backup-roundtrip-unavailable` is a retained diagnostic, not a pass;
exit zero only means that report was created. Do not automatically rerun or
change endpoints if unavailable. This checks one synthetic round trip, not
ongoing retention, scheduled backup coverage or production R1 protection.
See `docs/R1-BACKUP-ROUNDTRIP-20261111.md`.

## Offline capture handoff (Kali accepted)

The original handoff and its independent restore are accepted for synthetic
portability. The following documents that earlier operation; do not regenerate
the package for the fixed-input B2 check.

```sh
python3 -E -s -B -W error::ResourceWarning r1-data/handoff.py rehearse \
  --output-directory /absolute/new/handoff-run
```

This writes a four-message synthetic capture with a recorded restart gap,
exports a deterministic stored ZIP, and restores it locally with an externally
supplied expected checksum. Expected status:
`offline-handoff-rehearsal-passed-live-blocked`. Upload the **198-test offline
runner report**, `handoff-run/report.json` and `handoff-run/export/capture.zip`
for independent replay. The ZIP is synthetic and contains no real wallet/key.
Retain the entire new directory. No existing scanner or RPC inputs are needed.

The reusable `export` command accepts a closed R1 capture, creates a new private
output directory, and writes `capture.zip` plus `report.json`. The `restore`
command requires the original trusted report's `bundle_sha256`, the returned
bundle and a new output directory:

```sh
python3 -E -s -B -W error::ResourceWarning r1-data/handoff.py export \
  --capture /absolute/closed/capture --output-directory /absolute/new/export
python3 -E -s -B -W error::ResourceWarning r1-data/handoff.py restore \
  --bundle /absolute/returned/capture.zip \
  --expected-sha256 ORIGINAL_TRUSTED_REPORT_BUNDLE_SHA256 \
  --output-directory /absolute/new/restore
```

These are interface examples, not a request to locate or export production data.
Input bundles must be private regular files owned by the current user, with no
symlinks/hardlinks. Transferring to another machine may require a new private
copy there; never change an existing production archive to satisfy this rule.
The ZIP contains exactly a database and manifest, without compression, arbitrary
paths or links. Both package bytes and restored SQLite replay must match.

No remote service is called and no backup configuration is read. A successful
local restore leaves `off_machine_restore_verified: false` and
`remote_download_verified: false`. Independent-host replay and a storage-provider
upload/download receipt are distinct evidence still to collect. The existing
B2 scanner backup does not automatically cover these separate R1 packages.
See `docs/R1-CAPTURE-HANDOFF-20261111.md` and the consolidated
`docs/R1-SOURCE-VERDICT-20261111.md`. Full R1 and funded activation remain blocked.

## Bounded finalized block positions (Kali accepted)

The saved five-read result is accepted for its limited scope. No repeated public
ordering probe is requested; the following documents that earlier increment.

After the offline runner passes, use the **original** saved RPC report/bundle:

```sh
python3 -E -s -B -W error::ResourceWarning r1-data/ordering_probe.py \
  --rpc-report /absolute/existing/rpc-run/report.json \
  --evidence /absolute/existing/rpc-run/evidence.json.gz \
  --output-directory /absolute/new/ordering-run \
  --read-public-rpc
```

At most five public mainnet reads: genesis, one `getBlock` per distinct saved
slot (up to three), genesis again. Each block request uses finalized commitment,
`transactionDetails: signatures`, transaction version 0 and `rewards: false`.
No transaction bodies, outcomes, balances or prices are requested. A block's
public signature list is retained to reproduce its zero-based transaction
positions. The list includes signatures of other transactions in that block.
Inputs pass the existing checksum/source/replay/schema/accounting checks first.
One-MiB response and 8,192-signature bounds apply. The fixed endpoint, thirty-
second network budget, five-second request limit, no retry/redirect/proxy rules
remain in force. Only the new private output directory is written.

Expected: `finalized-block-positions-reconciled-live-blocked`. The sample's
primary signature must appear exactly once in its reported block. Record keys
combine slot, block-list position and previously saved instruction indices.
This is provider-reported record ordering, not wall-clock timing, feed arrival
order, complete history, gap recovery or independent consensus verification.
Unrequested full transaction/reward bodies are discarded and stop the probe.
Unavailable blocks produce `block-ordering-unavailable`; a valid block missing
a selected signature produces `selected-transaction-missing-from-reported-block`.
Neither grants acceptance. Exit zero only means a diagnostic was retained.

Upload the **181-test offline report**, plus this new directory's `report.json`
and `evidence.json.gz`. If unavailable, upload once and do not automatically
retry. Offline replay replaces `--read-public-rpc` with
`--replay-evidence /existing/ordering-run/evidence.json.gz`, uses the same original
RPC inputs and a different new output directory. It requires no network.
See `docs/R1-BLOCK-ORDERING-20261111.md` for limits and the remaining R1 decision.

## Bounded deployment metadata probe (Kali accepted)

The saved five-read deployment result is accepted for metadata scope. No repeat
public deployment probe is requested for the ordering increment. The following
command documents that earlier step.

After the offline runner passes, use the original saved RPC report/bundle:

```sh
python3 -E -s -B -W error::ResourceWarning r1-data/deployment_probe.py \
  --rpc-report /absolute/existing/rpc-run/report.json \
  --evidence /absolute/existing/rpc-run/evidence.json.gz \
  --output-directory /absolute/new/deployment-run \
  --read-public-rpc
```

This makes at most five requests to the fixed public mainnet endpoint: genesis,
Pump/Pump Fees program pointers, both programs and their ProgramData headers in
one batch, a second batch of those four accounts, and genesis again. Each account
request uses finalized commitment, a nondecreasing minimum context at least as
recent as every saved transaction, and a 49-byte slice. The preserved HTTP client
has five-second per-request deadlines within a thirty-second network budget,
one-MiB response caps, disabled redirects/proxy inheritance and no retry/fallback.
No sudo, Docker/database access, wallet/API key, fee configuration fetch,
simulation or transaction submission is used. This is a public read, not a paid
PumpPortal subscription. The existing scanner connection is untouched.

Before any network call, the original inputs must still pass checksum, RPC
replay, schema and accounting checks. Only one to three accepted transaction
slots are used. Program account owner/executable/size/tag and ProgramData
owner/size/tag/option/ELF prefix must match the supported loader-v3 layout.
Pointers, headers and allocated sizes must be stable across the two snapshots.

`deployment-metadata-predates-sample-live-blocked` means both reported last
modification slots are strictly earlier than every saved transaction, with the
metadata rechecks completed. `historical-deployment-window-unresolved` means at
least one modification is at or after a sample: current metadata cannot bind
that sample to the current deployment. Same-slot changes remain unresolved.
`deployment-metadata-unavailable` covers unavailable, inconsistent or unsupported
responses. Upload the result even if unavailable; do not automatically rerun it.

None of these states verifies executable bytecode, SDK/source equivalence,
historical fee configuration, ProgramData PDA derivation or the full dependency
chain. A header hash is not a bytecode hash. `minContextSlot` is a lower bound on
the current read, not a request to retrieve historical state.

The new private output directory contains `report.json` and `evidence.json.gz`.
Upload both plus the 167-test offline report. The raw snapshot contains public
program headers only, including public upgrade-authority addresses, and can be
replayed without new network calls. For offline replay, replace
`--read-public-rpc` with `--replay-evidence /existing/deployment-run/evidence.json.gz`
and use a different new output directory. Source inputs stay the original RPC
files, not the deployment probe's output files. The replay repeats the exact
request sequence and compares the binding to those source inputs. A copied or
edited local bundle is not independently authenticated chain evidence.

See `docs/R1-DEPLOYMENT-METADATA-20261111.md` for the accepted Kali evidence.
The existing R1 effort cap and live-collection block remain unchanged.

## Offline native-SOL accounting inspection

Run after the acceptance runner against the same saved RPC report/bundle:

```sh
python3 -E -s -B -W error::ResourceWarning r1-data/accounting_inspect.py \
  --rpc-report /absolute/existing/rpc-run/report.json \
  --evidence /absolute/existing/rpc-run/evidence.json.gz \
  --output /absolute/new/accounting-report.json
```

This first replays the accepted strict inspector and schema comparator. It
supports one creation and at most one direct native-SOL buy_v2 in a transaction,
with no cashback, holder rewards, shareholder split, retained creator fee or
quote transfer fee. Other modes remain unsupported. It checks exact buy argument
length, event order, distinct payment roles, fee-recipient identity, reported
fee-rate arithmetic, creator/protocol/buyback transfers, instruction cost cap
and creation-to-trade reserve arithmetic. The 36-field profile remains diagnostic;
neither a historical program binary nor fee configuration has been authenticated.

Every parsed System transfer/createAccount is counted once, with the network
fee charged to the first account. Expected net changes are compared with every
pre/post lamport balance. Unknown System instructions, missing balances, duplicate
keys/groups, noninteger amounts and unaccounted net changes cannot pass. Matching
net balances do not prove that every internal program operation was observed.

The reported creator fee must match one unambiguous transfer; additional vault
transfers are shown separately with unknown purpose. Account creation outflows,
trade-plus-reported-fees, full buy-parent outflows, network fees and the whole
transaction's wallet debit remain distinct. No rent-exemption or recoverability
claim is made. A combined create-and-buy debit is not a repeat-trade cost model.

Expected report status: `offline-accounting-inspection-complete-live-blocked`.
For the saved three-case bundle, cases 1 and 3 have
`observed-accounting-consistent-live-blocked`; case 2 has
`creation-only-accounting-consistent`. All three have zero net-balance residuals;
both trades pass 16 arithmetic/identity checks. Exit zero means a diagnostic was
written; mismatches/unsupported cases remain explicit, not acceptance. Upload
this report and the runner report from the same pinned checkout. No sudo, fresh RPC request,
funding, scanner change, ML fit or deployment is part of this check.

See `docs/R1-NATIVE-ACCOUNTING-20261111.md` for findings and remaining limits.

## Offline trade-schema comparison

Run after the acceptance runner, using the same saved RPC files:

```sh
python3 -E -s -B -W error::ResourceWarning r1-data/schema_compare.py \
  --rpc-report /absolute/existing/rpc-run/report.json \
  --evidence /absolute/existing/rpc-run/evidence.json.gz \
  --output /absolute/new/schema-comparison.json
```

This separate diagnostic retains the accepted inspector and `pump_schema.json`
unchanged. It first repeats that inspector's provenance, replay and transfer
checks, then compares TradeEvent with the 36-field definition extracted from
the documentation labeled `pump-rust-client` 0.5.0. The first 35 fields match the
old profile exactly; the additional field is `quote_transfer_fee: u64`. The
extracted profile is SHA-256 pinned. The upstream page uses a mutable `latest`
URL, whose displayed version and reported source revision were recorded; no
crate archive checksum or historical deployed program version was verified.

All bytes must decode and re-encode exactly, and mint/user/direction/token/SOL/
quote fields must match the retained native-SOL buy evidence. Missing or extra
bytes and conflicting evidence remain unsupported. A nonzero extension is
decoded literally, not treated as a validated fee model. The parent `buy_v2` and
event-reported `buy` names remain separate observations; no alias is assumed.

Expected diagnostic status: `offline-schema-comparison-complete-live-blocked`.
For the accepted three-case bundle, cases 1 and 3 each have
`exact-layout-and-transfer-match-diagnostic-only`, 390 consumed bytes, exact
re-encoding and reported quote transfer fee zero. Case 2 has no trade in that
transaction. Exit zero means a comparison report was written, not that all cases
match or that reconstruction passed. Pair this report with the acceptance runner
report from the same pinned checkout. No new RPC request, sudo, wallet funding or scanner change is needed.

See `docs/R1-TRADE-SCHEMA-COMPARISON-20261111.md` for source provenance and scope.
Fee/reserve accounting, version applicability and full R1 remain open. This is
within the existing five-working-day R1 cap, not a new gate or deadline extension.

## Offline event inspection of existing RPC evidence

This increment needs no new RPC call, sudo, wallet, API key or container action.
Use the existing successful RPC `report.json` and its `evidence.json.gz`:

```sh
python3 -E -s -B -W error::ResourceWarning r1-data/event_inspect.py \
  --rpc-report /absolute/existing/rpc-run/report.json \
  --evidence /absolute/existing/rpc-run/evidence.json.gz \
  --output /absolute/new/event-report.json
```

The inspector checks compressed and decoded hashes, source pins, RPC replay and
request accounting before inspecting the transactions. Input caps are 128 KiB
for the RPC report, 16 MiB for compressed evidence and 32 MiB after decompression.
Symlink inputs and output replacement are refused. Output is private and atomic;
inputs are preserved. No raw mint, wallet, metadata name/URI or signature is exported.

`pump_schema.json` is a minimal mechanical extraction of CreateEvent, TradeEvent,
Shareholder and create_v2/buy_v2 account definitions from the official Pump IDL at
commit `639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22`. Its hash is pinned in the
inspector. Every event byte must be consumed; trailing bytes, including zeroes,
are a schema mismatch. This pins a documentation schema, **not** the deployed
program binary/version. Parent instruction arguments are not decoded or certified.

Supported event provenance is a direct Pump create_v2/buy_v2 parent (fixed program
and account layout), followed by a Pump self-CPI with the Anchor event tag,
matching event discriminator, stack height and parent event-authority account.
Each Pump parent must have exactly one supported event. CPI wrappers, non-native
quote remaining accounts, other instruction versions and unknown events stay
unsupported. Log copies are not counted as additional events. These checks are
consistency checks on retained provider evidence, not cryptographic authentication.

Creation fields are exported only after exact decoding and mint/curve/user/token
program agreement with parent accounts. MintTo totals are reported separately
from the creation event's supply. For supported buy parents, parsed token/SOL
transfers can be inspected independently of unsupported trade-event tails; these
transfers exclude fees/rent and do not establish total acquisition cost. A case
with no trade event describes that transaction only, not all activity after creation.

Expected diagnostic status is `offline-event-inspection-complete-live-blocked`.
It means inspection completed, **not** that every event decoded or reconstruction
passed. Inspect each case. The accepted three-case RPC bundle currently yields
three exact creation events and two trade events with eight unconsumed bytes each;
the latter are explicitly `schema-mismatch`, without exported partial trade values.
One Mayhem case has two MintTo operations totaling twice its event-reported supply.
Do not normalize that difference away or infer fees from unmatched event bytes.

Upload the offline runner report and the new event report. Keep the original
RPC artifacts unchanged. No rerun of the public RPC probe is required. Schema
resolution and economic reconstruction remain open even after Kali inspector acceptance.

## Public RPC feasibility probe on Kali

After the offline runner passes, run the separate read-only probe from the same
pinned checkout, using a **new output directory**:

```sh
sudo python3 -E -s -B -W error::ResourceWarning r1-data/rpc_probe.py \
  --project "$HOME/apps/solana-early-alpha-radar" \
  --output-directory /absolute/new/rpc-run --read-public-rpc
```

This command makes public network requests. It reads no wallet, API key or
environment credential and uses only `https://api.mainnet.solana.com` with proxies,
redirects, retries and endpoint fallbacks disabled. It never signs, simulates or
sends a transaction. Sudo enables local Docker/volume reads; output ownership is
returned to the invoking user. There is no container restart or scanner change.

The indexed SQLite read selects up to three distinct valid creation signatures
and mints aged two minutes to 24 hours, examining at most 32 rows of at most
4096 bytes under a three-second read deadline. The existing local Docker discovery
has two five-second command timeouts. The network phase has a 30-second budget,
five-second wall-clock timeout per call, one-MiB response cap and at least 0.5 seconds
between calls. It makes at most nine read-only RPC calls: mainnet genesis before,
one signature-status batch, up to three transaction/account pairs, genesis after.
Any transport/envelope failure stops further network traffic. Public capacity,
retention and access are not guaranteed; 403/429 is unavailable evidence, not token
failure and not a reason to retry or switch to paid access automatically.

Reconciliation requires finalized successful status, matching transaction signature
and slot, parsed mint membership, exactly one standard SPL Token/Token-2022 mint
initialization, and matching decimals/owner/initialized state in a finalized mint
account at or beyond that slot. Decimals are read from evidence. Provider responses
are not independent cryptographic proof or verified Pump creator identity. Current
account state does not reconstruct historical curve state or intra-slot order.

Upload `report.json`. Keep the private `evidence.json.gz` alongside it locally.
The report pins compressed and decoded evidence hashes; successful reconciliation
processing is replayed from the saved bundle without network access. The summary
omits mint/signature/wallet identities. The private bundle retains public-chain
responses and selected source identities; off-machine preservation remains open.

`rpc-facts-reconciled-live-blocked` means every selected case passed these narrow
checks. Inspect the selected count: one to three cases cannot establish general
coverage or capacity. `rpc-feasibility-incomplete`, `probe-unavailable` and
`no-eligible-creation-records` are non-passes; upload the summary without rerunning.
Exit zero means a diagnostic report was created, **not** source acceptance. Only
`check.py` is the offline pass/fail runner. Full R1 and paid activation remain blocked.

## Source metadata probe on Kali

After offline checks, run the separate probe with the application project path:

```sh
sudo python3 -E -s -B -W error::ResourceWarning r1-data/source_probe.py \
  --project "$HOME/apps/solana-early-alpha-radar" --output /absolute/new/source-report.json
```

The project folder need not contain Git metadata. The probe uses only local
Docker socket inspection, filtered by the Compose working-directory and radar
service labels, to locate `/app/data`. It does not load `.env`, inspect container
environment values, restart containers or open a provider connection. Sudo is
needed to read Docker's named volume; only the probe needs it. Under sudo, the
private output is assigned back to the invoking user.

The database is opened `mode=ro` / `query_only`. The read transaction is bounded
to three seconds, 128 recent creation records and 4096 bytes per record using the
existing receipt index; no fallback table scan is allowed. Docker discovery has
two five-second command timeouts. The report exports non-null/absent field counts
and timing only, not source payloads, signatures, wallet addresses or outcomes.
Field presence is not field validity or chain verification. SQLite may use its
normal WAL read coordination; the tool performs no row/schema changes.

`creation-metadata-observed` means some existing creation metadata was read.
`creation-metadata-insufficient` and `source-metadata-unavailable` remain explicit
non-passes. All three states retain `source_complete: false` and
`live_activation_allowed: false`. Upload the source report even if unavailable;
do not substitute a guessed database path. `--database` exists for explicit
verified paths and synthetic tests, not automatic discovery fallback.

## Transport controller boundary

`transport.run_session` accepts an injected asynchronous wire. It opens at most
one session, serializes and rate-limits the four permitted subscription methods,
expires watches even during silence, unsubscribes on migration, stops on gaps,
and aborts before bounded cleanup when a capture limit is reached. It never
reconnects or treats a control message as proof of subscription acknowledgement.
Tests use only synthetic in-memory wires. There is no live launcher and no
WebSocket dependency to install for this increment. Real TLS/handshake/buffering,
provider compatibility, credentials and billing have not been exercised.

## Contracts

- The input interface accepts **bytes from an offline fixture/injected source**.
  A future transport must honor `tick()` during silence, stop consuming when the
  core stops, and invoke `gap()` on disconnect. No unattended live timing or
  network-buffer behavior is claimed by these offline tests.
- Default limits: 20,000 received messages (including discarded controls), 8 MiB
  raw payload, 64 KiB per frame, 48 hours, ten-minute planned watches, at most two
  concurrent and 24 daily planned watches, deterministic SHA-256 mint sampling
  at 1/64. These are conservative feasibility defaults, not a registered study.
- The SQLite main file is limited to 32 MiB; allow up to another 32 MiB plus
  journal headers during a transaction. Export and restore each need a separate
  additional bounded database copy. Future launch preflight must reserve this
  space and implement retention; this core installs no scheduled cleanup/backup.
- `ticks.db` is separate and private. A process lock prevents concurrent writers
  or exporting an active session. Counters, absolute deadline and terminal stop
  state persist. A clean restart records a gap and ends all prior planned watches.
  An unclean process exit stops the capture permanently when reopened. A transport
  disconnect also stops rather than pretending historical recovery exists.
- No automatic retry, top-up or new capture is performed on budget exhaustion.
  An explicit new directory is a new capture, not an authorized new spending
  allowance. These counters are not a provider billing enforcement mechanism.
- Creation sampling and capacity exclusions are recorded for every valid observed
  creation event. This describes the observed input stream, not all on-chain
  launches. Duplicate creation events are retained without creating a new watch.
  A signature is not used to collapse trades: one transaction may contain several
  events. Receive ordering is not asserted to be chain ordering or finality.
- Raw accepted event bytes, local receive timestamps and decisions have per-row
  SHA-256 and a chained digest. Replay also checks the materialized mint state
  against the event/gap history. Export uses a closed capture and a whole-file
  checksum manifest. Restore refuses replacement, altered bytes and extra members.
  Digests detect corruption relative to retained pins; they are not signatures
  authenticating a provider or protection against rewriting all local evidence.
- Unknown/malformed events, missing mint/signature identity, oversized frames,
  explicit provider errors, sensitive field names and known credential echoes
  stop capture. Provider error and acknowledgement text is discarded. A future
  transport **must supply its credential and relevant secret variants** through
  the in-memory `redactions` argument; no generic detector recognizes every secret.
  Never persist URLs containing an API key. No real credentials are needed here.
- Reports explicitly leave ledger order, initial state, subscription installation,
  billing-limit verification and profitability false. `watch-planned` is a plan,
  not an acknowledged provider subscription or proof of complete observations.

## Remaining before paid activation

Review the new Kali evidence; resolve the existing scanner/PumpPortal connection policy;
establish a viable verification path for required source fields, early-event
capture, ordering, finality and recovery; implement and validate the network adapter; agree the
explicit deposit and fee exposure; demonstrate off-machine preservation/restore.
Reuse the existing dedicated PumpPortal-linked wallet if suitable. Do not fund it
for this offline acceptance. A separate devnet rehearsal wallet is not the
provider-linked data wallet.

The paid pilot is intended to measure source quality, not to assume it is already
proven. Its limited discovery purpose and explicit budget require approval before
activation. Full evidence quality and reconstruction acceptance are prerequisites
for a confirmation study, not claims made by the metadata probe.

Development branch publication is allowed for Kali review. PR/CI consolidation
waits for the complete agreed gate and applicable Kali acceptance.
