# C1 metadata inventory — 10 November 2026

Base: accepted H1/early C1 main merge
`bc9507f723ad9f131aef4bb230403cfb36c61ccb` (PR #82).
The owner authorized the next bounded inventory after that consolidation.
This increment awaits Kali evidence; no new trial or model is authorized.

## Scope and repository findings

The existing `forward-study/experiment.py` pins the original frozen JSON artifact
to `016f8d0cf2b9c960e6dfa8406a4566e4473df2200e0040e95ab0480c44f50355`.
The original installation and closed availability confirmation each preserve a
model copy and sealed registration. Their actual presence/identity on Kali must
be checked, not inferred from committed code or earlier performance reports.

The old confirmation registration stores the union of frozen training tokens and
admitted development tokens across cohorts. It does **not** establish a complete
future exclusion list incorporating the later confirmation, B0/H1 inspections or
every other exposed dataset. Do not reuse it as a new-trial purge registry.

The quote-backup implementation verifies a ledger archive and keeps 14 local
archives. That code does not establish preservation of the private model,
registrations and original research captures, nor demonstrate a new study's
off-machine restore/replay. These remain separate evidence requirements.

## Read-only inventory

`availability-study/metadata_inventory.py` uses only Python's standard library.
It reads existing files; it imports no model, training or evaluation module and
needs no research virtual environment. It:

- Verifies the two model copies against the original pinned artifact, both sealed
  registrations, the model/protocol/source links, original reviewed-report and
  diagnostic pins, historical closed-window clocks and old exclusion-list binding.
- Exports counts and hashes of the known training/development token lists; no
  token identifiers, coefficients, source identifiers or private source paths.
- Catalogs at most eight captures in each known study directory and the two exact
  B0 captures already accepted for H1. B0 compressed index identities are pinned.
- Reads capture indexes as metadata and hashes compressed chunks against their
  indexed hashes. It never decompresses or parses chunk payloads. Byte verification
  is not full replay, outcome coverage or proof of which captures were reviewed.
- Shows uncovered requested detection-window intervals for the two old studies.
  Requested-window coverage does not establish uptime or complete observations.
- Refuses symlinks/hardlinks, unsafe private model/registration permissions,
  changed input identities, duplicate JSON keys, invalid clocks and broken chunk
  windows. Directory scans, metadata decompression, individual file sizes and
  total bytes are bounded; reads have a 60-second monotonic budget. No limit is
  raised by the operator command.
- Publishes one private, atomic, exclusive report outside source directories.
  Missing/invalid sources are reported with fixed scope/error codes where possible;
  nothing is repaired, created in source directories, re-registered or overwritten.

It accesses no live database, service, RPC or cloud storage. No Docker restart,
sudo, model evaluation, fitting, label analysis, new collection or transaction is
part of this increment. Raw byte hashes necessarily read compressed bytes, but
the capture outcome payloads are never decoded. Model/registration JSON is read
only for historical identity and token-list checks; no performance metrics are
recomputed or exported.

## Host inputs and result interpretation

Known paths, preserved from the accepted procedures:

- `/home/redeye/solana-radar-forward-experiment-20261022`
- `/home/redeye/solana-radar-availability-study-20261029`
- `/home/redeye/apps/solana-early-alpha-radar/radar-history-20261108T165920Z-4144732/capture`
- `/home/redeye/apps/solana-early-alpha-radar/radar-history-20261108T165935Z-4145895/capture`

Pass the `capture` subdirectories, not their enclosing report directories. The
November 8 capture log records these exact paths. The first November 11 C1 run
passed all 17 tests but could not find the two B0 indexes because its command
omitted this suffix; correct the input paths without replacing any evidence.

Use the separately supplied exact-commit Kali command; it creates an isolated
source checkout and output directory. On first validation, run the 17 inventory
tests and source hygiene check, then inventory these existing paths. For the
path-only correction, verify unchanged Python file hashes and source hygiene;
the accepted 17-test Kali result remains applicable. Upload the log and report.
If a source is missing or invalid, upload the partial report; do not substitute
a new capture, reset registration, change permissions or rerun model evaluation.

`inventory-complete-readiness-blocked` means every requested identity/byte check
completed. `inventory-partial-readiness-blocked` means a requested input/check is
unavailable or invalid. Both retain false gate/trial/model/live-use authority and
an incomplete future exclusion registry. A completed metadata report is not a
passed study-readiness gate. A top-level failure before report publication leaves
the sanitized validation log for diagnosis.

## Remaining decision after Kali

Review the returned identities, actual catalog and requested-window gaps. Within
the existing one-focused-engineering-day cap, return an inventory and explicit
unknowns or a blocked disposition. Do not expand into an indexer or repeated
outcome analysis. Reconcile the reported registration digests with earlier accepted
reports: valid self-seals and bindings alone do not prove historical provenance.
Later token membership still needs a separately scoped entry-only
projection/reconciliation, including confirmation and all subsequently exposed
data; original reviewed-capture membership also remains to be reconciled.

Before another trial, agree useful decision/numerical tolerances, estimate only
necessary preservation and evaluation changes, demonstrate off-machine recovery,
and define untouched future data with a dependence/sample contract. No duration,
sample target, new fit or new registration is authorized here. C1's December 31
scope/budget checkpoint and E0's independent blocked-state review remain unchanged.

Development publication is for Kali acceptance only. Consolidate this complete
inventory phase through PR/CI after host evidence is reviewed, following the
existing local-validation-first workflow.
