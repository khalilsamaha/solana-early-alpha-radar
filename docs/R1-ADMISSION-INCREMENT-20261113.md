# R1 supervised admission increment — 13 November 2026

The owner authorized continuing several engineering steps in one chain. This
increment connects five concrete boundaries without changing the accepted session
implementation: draft/source admission, stable single-attempt registry, private
synthetic credential and process delivery, independent completed-evidence review,
and read-only recovery. Detailed behavior and limitations are in
[r1-admission/README.md](../r1-admission/README.md).

## Implementation

- `admission.py` freezes the current draft before startup and binds exact hashes,
  limits, parent, output and registry. The durable claim is consumed before loading
  a credential or spawning. Failed credential loading/startup cannot free it, and
  changing the output path cannot reuse the same registry.
- `worker.py` uses the existing Linux containment/bootstrap and consumes a sealed
  generated credential before running the real reusable session and archive code.
  The default parent launches the existing Node scanner consumer on the Unix socket.
  All input is synthetic; no provider factory or real credential is accepted.
- Parent completion requires process reaping, exact request/contract/worker/archive
  bindings, receipt/limits checks and independent restore/replay. A clean process
  exit alone cannot grant completion. The original short offline limits remain:
  ten-second worker alarm, twelve-second parent budget and bounded reap.
- Read-only recovery does not execute a callback or write run evidence. Missing
  terminal receipts stay unresolved; failed attempts require reconciliation. A
  complete recorded offline result still refuses automatic resume and live launch.
- One portable bundle retains all five request/claim/draft/supervisor sets, three
  exact session archives and worker receipts, two fault-ready markers, report and
  log. Normal and idle succeed locally; cleanup failure remains a failed capture
  within complete evidence. Stalled and diagnostic-tainted children remain failed.

The existing eight-step service handoff coordinator is not relaxed. This increment
uses the existing stable ownership, credential, process and bounded cleanup
primitives but does not invent production lifecycle receipts. Actual direct-owner
shutdown, shared activation and explicit production rollback remain open.

## Validation performed

The final combined development batch on Python 3.12.14/websockets 17.4 passed:

- **15 integration tests**, zero failures/errors/skips, no detected diagnostics.
- **Five retained scenarios**; all children reaped. Stalled worker reached its
  specific marker and exited on SIGALRM (-14); the tainted-diagnostic worker reached
  its marker and exited 1 without an archive or completion receipt.
- Independent parent restore/replay for all three session scenarios. The deliberate
  cleanup failure remained `transport-cleanup-failed` throughout.
- Read-only recovery for all cases; unresolved/failed cases cannot resume.
- An independent portable-bundle review: exactly 30 expected members, report/log
  exact equality, claim/request/draft bindings, three archive manifests/receipts/
  journal replays, and exact worker receipt bindings.
- **163 source fingerprints** unchanged during this batch. All **157 previously
  accepted session fingerprints** still equal the uploaded Kali evidence from
  revision `aa3244c47221fa751f44d39c9b407d484390549e`.

Elapsed combined development batch: 17.141646 seconds. Status:
`admission-development-passed-unix-pending`. Development discovery endpoints were
explicitly simulated; actual workers, descriptor delivery, deadlines and process
reaping ran. Native Unix/Node verification of this new child boundary is pending.
No fresh Kali, RPC, B2, production or provider observation was performed.

Final local artifact identities:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| report.json | 22013 | `ddee4ca2a0df9cac6b832f09778779cdf72fa82c7a2e3d9fae3f90c9053731fb` |
| validation.log | 2298 | `ac587e836aba27f22933e5815768429c802c409c556d343db861a58ed0e4951f` |
| acceptance.zip | 378250 | `859342b121417403b5bff99d941ad25967974612de73257adbc2d5ef60351cb6` |

## One host validation and next boundary

Run the pinned `scripts/r1-admission-kali.sh` in a fresh isolated checkout. The
script installs only the existing hash-pinned dependency, applies source hygiene,
and bounds the whole batch to 180 seconds plus a ten-second kill grace. It uses
actual Node/Unix for normal, cleanup-failure and idle, plus the two explicit fault
cases. It does not repeat the unchanged 160-test session batch, Docker integration
or B2 round trip. Return one acceptance.zip; on failure keep all output and return
report.json and validation.log. No registry is reusable after an attempted run.

Required default status: `admission-offline-passed-live-blocked`, followed by
independent artifact review. This still leaves actual production handoff/rollback,
operator-bound global ownership, live supervision/provisioning, retention/capacity,
fixed measurement terms and numeric exposure authority before any real pilot.
No main merge, deployment, funding, signing, trading or provider activation occurs.

The original five-working-day total engineering cap is unchanged. This engineering
request is not a new allowance or an effort ledger. November 19 remains at risk,
no confirmation window has started, and December 31 remains the decision checkpoint.
E0 remains independent, blocked with holds preserved; last accepted operational
observation is November 9, 18:50:41 CET. The November 20 disposition still requires
actual closure evidence or remains blocked-with-holds-preserved.
