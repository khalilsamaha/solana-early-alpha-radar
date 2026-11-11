# R1 capture, transport controller and source feasibility probes

The capture core is Kali-accepted at `f92e4d1`; the offline subscription controller
and source metadata probe are Kali-accepted at `55ddf7a`; the bounded public RPC
probe is Kali-accepted at `d880134`. This fourth increment adds an offline event
inspector for the saved RPC evidence. It has **no live WebSocket adapter,
credential-file reader, trading operation, profitability evaluator or curve
reconstruction**. It cannot activate paid data. Only the separate RPC CLI below
opens a network connection; the acceptance runner remains entirely offline.
No change to the production scanner, frozen studies, E0 or CI is required.

## Kali acceptance

From a pinned isolated checkout, run:

```sh
python3 -E -s -B -W error::ResourceWarning r1-data/check.py --output /absolute/new/report.json
```

No third-party dependencies are needed. Linux/Python 3.11+ is required (flock,
private POSIX files and SQLite). The report must be a new path in an existing
directory. The runner executes all `test_*.py` checks and then a synthetic
capture/restart/budget-stop/export/restore/replay exercise. Tests use private
temporary directories and remove them afterwards. No scanner database, existing
capture, environment credential or wallet is read. Report contents include code
hashes and runtime versions, not raw provider payloads or credentials.

Expected status: `offline-event-inspector-passed-live-blocked`, zero failed/errored/skipped
tests, `local_restore_replay_passed: true`. This is not acceptance of feed quality,
an off-machine backup, reconstruction, billing, profitability or the full R1 gate.
Use `python3 -E -s -B -W error::ResourceWarning -m unittest discover -s r1-data -v`
for detailed local synthetic-test diagnostics if the runner stops.

The current suite contains 126 tests. Earlier 44-test, 72-test and 101-test Kali reports
remain accepted for their original pinned sources; they do not validate this addition.

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
