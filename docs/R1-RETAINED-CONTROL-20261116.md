# R1.A inventory acceptance and R1.B retained-container adapter

## Accepted supplied inventory

The supplied report ran on 16 November 2026 from 10:23:54.176867 to
10:23:54.686503 UTC (11:23:54 CET). Its SHA-256 is
`4ea99ddea22ab2be362d10544f1de7e23bca8556c054eb69288a9e857076cec6`.
The standalone JSON is byte-identical to `production-ownership.zip/report.json`.
All 22 source fingerprints match published commit
`59ffa4ed08c93db407ef7f0657899b1524e33676`. Its baseline report hash matches the
accepted readiness bytes, and all 19 unique container IDs match that census.
The scanner identity and exact 18-other-container review set reconcile. Five
Docker requests were reported. No production change or provider connection was
reported. This is supplied evidence, not independent live reviewer access.

The other workloads are 11 Supabase containers, five PentAGI-related containers
(including one terminal without a Compose project label), one Crawl4AI and one
MoneyPrinterTurbo. No second Radar-labelled workload appears. These names/images
identify declared workload roles, not validated behavior or global exclusivity.
Host processes, other daemons/machines and account connections were excluded.
The Docker metadata inventory substep is accepted; no unchanged rerun is needed.
Overall R1.A ownership remains unresolved.

## Changed R1.B boundary

The production candidate lacked a configuration-preserving stop/restoration
adapter: prior native control was limited to an inert isolated profile and the
handoff fixtures created a replacement actor. The new adapter retains the original
container ID, hashes complete engine configuration/mount metadata in memory,
uses the explicitly configured stop timeout, and checks before/after each operation.
Raw environment/command values are never journaled. It reuses the existing durable
journal writer through explicit profile hooks with a separate replay schema.

The implemented scope is direct-service suspension and explicit same-container
restoration. It is not yet connected to production admission or the shared-owner
shutdown proof. No live dispatch entry point is exposed. Engine running is not
application health; stopped is not a provider or billing acknowledgment. No
claim of cross-process/host/provider exclusive ownership is added.

Local validation: 21 new adapter/runner tests, 17 existing control tests, 20 handoff
tests and 51 deployment tests passed (109 total). Runner cases use a Docker state
model locally, not actual Docker. Source hygiene and shell syntax are checked
before publication. Docker is unavailable here. This is development validation,
not R1.C acceptance or evidence that the production scanner was stopped/restarted.

## Required next intervention

One changed-boundary Kali check, `scripts/r1-retained-control-kali.sh`, against the
pinned publication, using four newly created network-disabled inert containers in
the already accepted local image. Cases: normal same-ID restoration; lost stop
response; lost start response; configuration drift before restoration. Cleanup
receipts and full claims/journals must be returned in `results/acceptance.zip`,
including failure. No unchanged ownership/readiness/native-handoff rehearsal,
production action, provider/RPC connection or permission change is requested.

After acceptance, continue wiring observed target/preparation, shared shutdown,
finite live worker and preservation. No main merge, rollout, paid provider, funding,
trading or E0 change is authorized by this increment. Standing research-branch
publication authorization applies. The five-day historical focused-effort ledger
remains unquantified; no reset or remaining-allowance claim is made.
