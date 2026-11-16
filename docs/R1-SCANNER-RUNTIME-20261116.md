# R1 full scanner runtime check — 16 November 2026

## Current: supplied failure reviewed; narrow diagnostic required

The supplied attempt at `6270ada51ae04e1e0efbc6895286a327f764ee5c` ran
16 November, 17:45:41.191689–17:45:46.106080 UTC (**18:45:41–18:45:46 CET**).
Archive SHA-256: `5e7fbc76602cbb6900d01092d3d98ea638801d70a326c02f655d5889e162b963`.
Report SHA-256: `cb174d7a8f6bd18765e761cdede8dcd2cd266a9bc85d39fbdf36f73008455279`.
All 72 source fingerprints and eleven indexed members match. The full staged
candidate/manifest/Dockerfile reconcile with that revision. Eight Python and
eighteen Node tests pass. Image-byte verification succeeded for all sixty packaged
files in image
`sha256:55d2f2369e0a03835441a02ad9a65568a9288c3753aa276a89ff252c62eeac7f`,
manifest `bf330643bec5835413fbe85231f5bad876ecaf18a0b4c5e5618dcdddf8d7f694`.

The normal application failed `runtime-exit-unconfirmed`. Its created and running
configuration fingerprints differ (`1d364d95…` versus `1d64f0ff…`). The existing
check combined stopped state, exit code and configuration equality, and only
retained the application result/final state after that check succeeded. Therefore
the archive cannot establish which final condition failed or identify the changed
configuration fields. Do not assume the difference is benign Docker metadata.
Reaching that check implies the producer accepted its application result, but the
missing raw result prevents independent acceptance of health/statistics/shutdown.

Both newly owned containers have distinct identities and removal receipts; the
application attach client completed and threads joined. Its kernel peer UID/GID,
PID and parent match the recorded running container. Independent immutable SQLite
review returns integrity `ok`, three candidates, two launches and the expected
covering index. Those persisted rows do not establish full runtime closure. The
sequence-gap and missing-endpoint native cases were **not run**. This is supplied
historical evidence, not reviewer host access or a current production observation.

The checker now retains validated application results, final state and disposal
observations before evaluating closure. Bounded field-level fingerprints and
created-to-running/final differences preserve scalar flags and empty defaults;
arbitrary environment, command and path strings remain hashed. Exit uncertainty
and configuration drift have distinct failure codes. The exact configuration
equality gate remains intact: a changed fingerprint still fails. Twelve focused
tests pass, including modeled drift with preserved diagnostics, redaction,
existing-image source matching and refusal to create a deployment candidate from
a diagnostic-only run.

**Run only `scripts/r1-scanner-runtime-diagnostic-kali.sh` once**, from the newly
published pinned checkout named `source` in a fresh private review directory.
Do not rerun the original full build/check command below. This uses the fixed
already verified image above, creates at most one owned normal-case container,
and collects the missing field differences. It runs the changed twelve-test
checker suite; it does not repeat the unchanged eighteen Node tests, inert verifier,
other native scenarios or earlier combined handoff batch. There is no image build,
pull, source overlay, production service action or provider connection.

The historical image identity is reconstructed only if its full manifest hash
still matches the exact packaged bytes; checker-source pins remain distinct from
the image's recorded source revision. Missing/changed image or source fails without
a download or substitute. The same 50-second attach, bounded socket/inspect/cleanup,
private fixture storage and network-none isolation apply. This is one diagnostic
collection for a known missing observation, not a timing rehearsal or automatic
retry. Configuration drift may correctly return exit 1 again; return
**`results/acceptance.zip` regardless**. Preserve both review directories and IPC
paths. Do not prune the image or repair old evidence.

A diagnostic result never creates a deployment candidate or claims full runtime
acceptance. Review the actual changed fields and final state before deciding any
normalization or further changed-boundary test. Production and E0 remain unchanged.
The original full-batch instructions below are historical pending that review.

## Accepted input and changed boundary

The combined original/shared-session batch at `790e80536a28c11347fc2ba47d6d8871aea36def`
is accepted for its recorded boundary. Supplied observation: 16 November,
17:06:42.259190–17:08:05.155913 UTC (18:06:42–18:08:05 CET). All 231 source
fingerprints, 210 indexed members, seven control replays, five nested session
archives and twelve unique owned-container cleanup receipts reconcile. See
[the exact archive hashes and case dispositions](R1-COMBINED-ACCEPTANCE-20261116.md).
Do not rerun that accepted batch unchanged. These are supplied historical host
artifacts, not reviewer access to Kali or a current operational observation.

That batch used scanner modules inside the previously accepted image. It did not
start the actual application entry point, its HTTP server, storage and statistics
worker together. This increment prepares that separate check using a new image.

## Source corrections

Shared discovery health now reports enabled/waiting/success/gap without requiring
an upstream API key in the consumer. Direct mode keeps its existing key behavior.
The application validates a shared Unix endpoint before opening storage or starting
background loops; the adapter still rechecks immediately before connecting.
Dashboard-only mode remains independent of a discovery endpoint.

The statistics manifest pins the three changed source files. The preceding exact
cache provenance `86ad1258abf101c20935f76585e5c64a9a48c7d46b96b522ce3a5a2d66a99cb3`
is retained as compatible: these changes do not alter stored event interpretation,
compaction or statistics calculation. Regression coverage verifies preservation
of cache identity and rows across adoption. No production cache is read or migrated.

Local validation: **232 scanner tests and 30 image/runtime tests pass**, without
skips. The runtime tests model Docker while exercising real fixture SQLite replay
and thread coordination. A separate attempted full-application Unix-socket probe
could not start its listener (`PermissionError`); it provides no application or
container acceptance. Docker is unavailable here. Native image execution remains
unverified until the supplied Kali result is reviewed.

## Original full-batch invocation — do not repeat unchanged

Run `bash scripts/r1-scanner-runtime-kali.sh` once from the published pinned checkout
named `source`, in a new private review directory. It first runs eight runtime
regression tests and eighteen focused Node startup/adapter tests. Missing Node,
Docker, the existing base image or local endpoint access produces a failed result;
do not install, change permissions or retry to bypass that result.

The existing immutable local base is
`sha256:786529348e5b7b6563a33d8c358c3d03c97110879d6ad53af0fbae65cd0249f9`.
One image build uses the exact staged source, network none, no pull and no downloads.
The default command verifies packaged bytes only. The old accepted image and its
receipts are unchanged. There is no source bind mount or production data mount.

At most four uniquely owned disposable containers run:

| Case | Required evidence |
| --- | --- |
| Image default | Packaged bytes and source manifest verify; no service starts |
| Normal application | Actual `scanner/src/index.js`; three synthetic discoveries, two launch rows, three candidates; EOF becomes one gap; loopback health and successful statistics worker; real SIGTERM handler stops loops and closes storage |
| Sequence gap | Out-of-order first frame produces one gap and no discovery/launch/candidate records; statistics worker and shutdown still complete |
| Missing endpoint | Actual startup refuses before creating storage or attempting public HTTP/upstream access |

The two running application cases start with an empty private directory. The probe
prepares a new fixture database and its exact statistics covering index before
importing the actual entry point. That prerequisite is explicit in each result;
this does not test production index provisioning or authorize a migration.
Missing-endpoint creates neither the fixture database nor the index.

Application containers use UID/GID 1000, network none, a read-only root, no added
capabilities, no-new-privileges, no published ports, no restart, 512 MiB memory/swap,
one CPU and 64 PIDs. Only a fresh read-only private IPC mount and fresh writable
fixture data directory are supplied. The inert verifier retains its existing
128 MiB/32-PID profile. No real credentials are loaded. The probe blocks public
fetches and upstream WebSocket construction; only its own loopback HTTP checks
are permitted. Blocked public-fetch attempts are counted, not labelled requests
that reached a provider. Overall market readiness must remain false.

Before synthetic frames are sent, kernel peer UID/GID/PID and process parent must
match the exact running container generation. Durable create/start intents precede
application container actions. Cleanup removes only the matching newly owned
identity; uncertain cleanup stays failed. After removal and client/thread joins,
the host independently reads fixture SQLite with read-only immutable access and
reconciles the counts and unchanged bytes.

The image build client has a 120-second bound; application attach has 50 seconds;
the health condition has a 12-second bound. Socket/metadata/cleanup operations have
their source-defined finite deadlines. The actual application retains its
30-second forced-exit watchdog; these containers declare a 35-second Docker stop
timeout, but normal acceptance invokes the actual in-process SIGTERM handler.
This is not a worst-case shutdown, resource adequacy, soak or timing-margin proof.
It does not resolve the separate production 35-second stop versus 30-second
manifest ceiling. There are no automatic retries or repeated timing rehearsals.

Return **`results/acceptance.zip`**, including on failure. It contains source pins,
image identity/manifest, test results, bounded build diagnostics, application
receipts, disposal evidence and indexed member hashes. SQLite is exported only
after confirmed removal and thread joins. Preserve the review directory, image,
build context and `/tmp/r1-app-*` directories named in receipts; do not prune,
repair or delete partial evidence. Expected success is
`scanner-runtime-offline-passed-live-blocked`.

## Remaining work

Even a successful result closes only this offline application boundary. Full R1.C,
production original/shared-owner handoff, global ownership, live credentials and
resources, remote evidence preservation, exact pilot terms and rollout remain
open. No live pilot or confirmation clock starts, and the historical effort cap
is not reset. Research-branch publication is authorized; production activation,
main merge and spending are not part of this change.

E0 remains independently blocked with holds preserved. Its last accepted RPC
observation is November 9, 18:50:41 CET; this work supplies no new balance, receipt
or historical-coverage evidence. The November 20 disposition remains blocked with
holds preserved unless required closure evidence exists, reopening only on exact
finalized receipt evidence, credible complete history under a reviewed closure
policy, or a specific journal discrepancy permitting bounded reconciliation.
