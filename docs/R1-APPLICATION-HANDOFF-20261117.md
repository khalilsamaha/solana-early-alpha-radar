# R1 full application and retained restoration — 17 November 2026

## Accepted supplied native evidence

The supplied `acceptance(20261117-054923).zip` is independently accepted for the
combined offline application/finite-owner/retained-restoration boundary. Its
recorded observation is **17 November 2026, 06:48:00–06:48:20 CET**
(`05:48:00.862476–05:48:20.639830 UTC`), at published source
`56647b5f40f4909feafa8536687d57540a70860b`.

| Evidence | SHA-256 |
| --- | --- |
| Supplied archive | `7b705f57d5c7fce5e03d17db13a23ed2e56793fdd6dad430e993d85a716413f4` |
| Report | `3c154bc041d31ce80a7af3a5b6cb7edd747f768ddf95f9c4a034096632e2a2de` |
| Member index | `ecbc762a7e1c467744378fb88e6fafb1ecce947021f8e325ab5bf320cbd75762` |

Review reconciles all **238 source pins**, **142 indexed members**, the 17 passing
host-side regression tests, four control journal replays, four independently
replayed capture archives, native endpoint/peer/container-generation bindings,
application package/results, and eight distinct owned container disposal receipts.
Fixture SQLite was independently opened read-only/immutable from scratch copies;
all four copies pass integrity checks and contain three candidates/two launches.
Research retires at two delivered discoveries; the third arrives before final
closure. Storage, statistics and shutdown receipts reconcile with the accepted
image. No provider connection or production mutation is claimed.

| Case | Independently verified result |
| --- | --- |
| Normal | Same original ID/configuration/restart policy restored after durable shared closure; both owned containers subsequently disposed |
| Lost application confirmation | Application itself closes, but supervisor remains failed; no original start and no shared completion receipt |
| Lost shared confirmation | Supervisor succeeds, but missing durable bridge confirmation prevents original start |
| Changed application storage | Pre-change and changed SQLite have identical records/counts; `user_version` changes 0 to 17 and exact bytes differ; original start is refused, leaving a pending start intent |

A clean capture archive does not erase the two lost-confirmation failures or the
changed-application-storage refusal. Those refusals are the required outcomes of
the fault cases. Disposal of an owned fixture does not complete a pending control
transition.

**No unchanged Kali rerun is needed.** This review inspected an uploaded historical
artifact; it did not connect to Kali or query a live host/RPC. The evidence accepts
only the combined offline boundary. Production ownership/resource adequacy, remote
preservation, live pilot terms and E0 closure remain separate and blocked.

## Implementation scope

The previously accepted full scanner application image connects to the existing
finite shared owner and retained-original restoration gate. This is research-branch
engineering under the continuing authorization, not production activation, full
R1.C completion, E0 closure or a live pilot. Earlier standalone application and
module-consumer handoff acceptance remain valid at their recorded source revisions.

## Exact integration

The manifest now separates the retained original's `scanner_image` from the
application's `shared_scanner_image` and `shared_scanner_manifest_sha256`.
`session-application-normal` requires these fixed accepted identities:

| Role | Identity |
| --- | --- |
| Newly created inert original | `sha256:8c6e3458333f587cb1a5110dbfdc2d6c98f2bdcc6892eb589ee08cf8b9b66140` |
| Full application | `sha256:55d2f2369e0a03835441a02ad9a65568a9288c3753aa276a89ff252c62eeac7f` |
| Application package manifest | `bf330643bec5835413fbe85231f5bad876ecaf18a0b4c5e5618dcdddf8d7f694` |
| Application source tree (60 packaged files) | `be15ea96816aaae67339cfe94539d6eca52a090a` |

No image rebuild, pull or source overlay is used. The application runs the already
accepted `/app/runtime-probe.mjs normal`, including actual `scanner/src/index.js`,
fresh fixture SQLite/index provisioning, statistics worker, loopback HTTP health,
EOF gap handling, actual SIGTERM handler and storage closure. All market readiness
and activation claims remain false. Three distinct synthetic discoveries yield
three candidates and two launch records; the third discovery follows research
retirement. The synthetic worker cannot rearm research or open an Internet socket.

The existing private endpoint and kernel peer PID/UID/GID/parent checks bind the
consumer to its owned container generation before upstream fixture admission.
An application result must bind the accepted package and confirm shutdown;
independent immutable/read-only SQLite replay checks integrity, counts and exact
bytes. The controller rechecks the retained SQLite evidence before restoration.
Matching row counts alone are insufficient. Original restoration still requires
same-invocation completion, durable bridge confirmation, joined/reaped actors,
and unchanged evidence. Historical inspection never reconstructs start authority.

## Historical Kali invocation — accepted; do not repeat unchanged

Use a fresh checkout of the exact published handoff commit, named `source`, inside
a new private review directory. Run once:

```bash
bash scripts/r1-application-handoff-kali.sh
```

The script accepts no production container selector, credential path, provider
endpoint, image override or remote destination. It runs the focused application
and controller model tests, then only these four new combined cases:

| Case | Required disposition |
| --- | --- |
| Normal application | Full app and finite owner close; same owned original ID/configuration/restart policy restore |
| Lost application confirmation | App actually closes, but withheld return leaves supervisor failed and prevents original start |
| Lost shared confirmation | Successful supervision without a durable bridge receipt prevents original start |
| Changed application storage | After closure, a deliberate fixture-only SQLite metadata change preserves counts but blocks original start; pending intent remains explicit |

At most **eight newly owned containers**, two per case, are created. All have
network none, a read-only root, UID/GID 1000, dropped capabilities, no-new-privileges
and no published ports. The original has no mounts. The application has only a
fresh read-only IPC mount and a fresh writable fixture-data mount; it has 512 MiB
memory/swap, one CPU and 64 PIDs. Its restart policy is `no`.

The worker has an 18-second aggregate wall budget (10 setup + 3 service + 5
shutdown), 512 MiB address space, ten CPU seconds and 64 descriptors. CLI calls,
startup conditions and cleanup have finite source-defined bounds. Application
SQLite is limited to 256 KiB for evidence; fixture storage is assessed against
2 MiB with a fresh 8 MiB free-capacity minimum. These are checks, not a filesystem
quota or reservation. Evidence export is bounded to 32 MiB. This is not a soak,
worst-case shutdown or timing-margin claim. The existing application 30-second
watchdog and 35-second declared stop timeout are unchanged; the separate production
35-second stop versus manifest 30-second ceiling remains unresolved.

There is no automatic retry or timing rehearsal. Only the exact newly owned
containers may be stopped, restarted or removed. Production data, E0 journals,
holds and balances are outside the test. No real credential, provider or RPC
connection is used. Missing prerequisites produce a failure for review; do not
install, fund, adjust permissions or rerun older accepted checks to bypass it.

Return **`results/acceptance.zip`**, including on failure. Retain the review
directory and `/tmp/r1cs-*` registries named in its artifacts. The archive contains
source pins, per-case timestamps, controller/bridge/supervisor receipts, native
identity/peer records, disposal evidence and member hashes. Application SQLite is
copied only after confirmed removal and client reaping; unavailable snapshots are
labelled explicitly. The storage-change case retains both pre-change and changed
bytes. A clean capture archive cannot promote failed application/restoration
status. Local export/restore proves no remote preservation or retention policy.
Expected batch status is `combined-control-offline-passed-live-blocked`.

## Validation and remaining work

Local checks cover manifest image separation, actual finite-owner retirement and
three discovery envelopes, application receipt/isolation validation, modeled
container lifecycle and owned cleanup, independent SQLite replay, changed-byte
restoration refusal, lost application/bridge confirmation, and evidence packaging
when cleanup cannot be confirmed. Existing deployment, image/runtime, supervision
and retained-control regression suites also pass. Local models are not Docker or
kernel-peer observations. The supplied archive above now establishes the scoped
native acceptance at its recorded observation time.

After acceptance, production original/shared-owner ownership, resource adequacy,
live credentials/provider behavior, remote preservation and exact pilot terms
remain separate gates. No production rollout or engineering-cap reset is claimed.

E0 remains **blocked with holds preserved**. This integration supplies no fresh
Kali/RPC observation, current balance, exact finalized receipt or credible complete
historical coverage. Its last accepted operational observation remains November 9,
2026, 18:50:41 CET. On November 20, completion requires the missing closure evidence;
otherwise the disposition is blocked with holds preserved. Reopen on an exact
finalized receipt, credible complete historical evidence under the reviewed closure
policy, or a specific journal discrepancy enabling bounded reconciliation. Repeated
RPC absence, expired blockhashes and matching balances do not prove non-execution.
