# R1 combined offline admission, shutdown and finalization

The preservation increment is accepted on Kali at
`f2db8ff9073a628748dc6f0c82cdfaf1a03205c7`: 314 core checks, 18 preservation
checks, all 153 matching source hashes and all three archives independently
verified/restored with identical member bytes and classifications. The complete
archive replays; killed-writer and SQLite-transaction evidence remain quarantined.
All fixture processes were reaped. Full runner: 26.176248 seconds.

Exact Kali evidence hashes:

- Report: `7901f7b538178678d17b8a2fdd9827c34d4336a751c760c9c713e62099b0b882`.
- Complete (63,853 bytes): `0c8306f26ab724f325eb987caee5a27a07e8ec19ac1ffcf00904cad4e8f9f5dc`.
- Interrupted (59,413 bytes): `0c91250f889a94a9b091a677fe51b210de1db4dfecd9fa6a04c9a5e4ec080827`.
- SQLite rollback (68,328 bytes): `02a657c993d868b6889d9c094db9e0fdb5505aac92f0be0b9cddd136d9044c4c`.

## Combined run

This increment connects the existing actual synthetic broker/scanner service
adapter, durable lifecycle, frozen draft contract and preservation implementation.
It replaces no accepted component and changes no production scanner configuration.
It has no live mode, real credential input, funding, provider connection, signing,
trading or approval-writing interface. Its admission is explicitly for one offline
rehearsal; the measurement draft and numeric exposure remain unapproved.

Within one private stable control directory, the runner:

1. Validates the exact frozen contract and source bindings before any actor starts.
2. Locks the control directory and exclusively/fsyncs `admission.json`, consuming
   the only allowance before runtime effects. It then writes the lifecycle claim,
   also before the first actor. The claim binds the contract hash and contract
   source digest; admission separately binds the entire orchestration source set.
3. Executes the accepted eight-step handoff with actual broker/scanner components.
   In default Kali mode only generated, ownership-verified disposable containers
   receive Docker operations. Production identity observation remains read-only.
4. Unwinds all owned processes/containers. `cleanup.json` retains observed actor
   identities even if cleanup fails; it alone is not a successful cleanup receipt.
   Unconfirmed cleanup prevents preservation and completion.
5. After the lifecycle releases its registry lock, writes a durable
   `finalization-intent.json` binding admission, cleanup observations, lifecycle
   bytes and contract. Rechecks sources before accessing the preserver.
6. Preserves the quiescent source and independently restores/verifies the archive.
   Complete lifecycle evidence must replay; an interrupted lifecycle must remain
   quarantined. The original sources remain unchanged.
7. Exclusively writes `completion.json` **last**, binding admission, finalization
   intent, cleanup, archive and both preservation/restore reports. Failed archive,
   restore or receipt writes never receive completion status and cannot retry.

The receipt finalizes **evidence**, not a trading/measurement gate. A quarantined
run can have `finalization_complete: true` while `operation_complete: false` and
`reconciliation_required: true`. Unsubscribe failure may yield a complete evidence
archive of a failed research session: replayability is not a quality pass.

The handoff's direct-mode restoration occurs only on its confirmed sequence and
before finalization. Failure to archive afterward does not erase that history,
pretend the handoff never ran, or trigger another restoration. The stable control
remains consumed. An operator choosing/deleting another control directory is not
prevented by this cooperating-run lock; a future live deployment needs its fixed
reviewed registry/configuration and separate authorization.

## Reconciliation and failures

`inspect()` is read-only. It opens existing files/locks but creates no files or
locks, performs no database replay, invokes no adapter, and never resumes,
retries or restores a service. It checks current source pins, all durable receipt
bindings, archive/member bytes, restored files and original snapshot bytes.
Missing, changed, noncanonical, busy or inconsistent evidence requires
reconciliation. Valid finalized quarantine still requires reconciliation.
Inspection reports its narrower scope explicitly: stored receipt/byte bindings,
not a new independent replay. Full replay remains the preserver/restore operation.
Hashes are integrity bindings, not authenticated operator signatures.

The unit suite injects preservation, restore, receipt-publication, cleanup and
source-drift failures. It checks consumed admission, invalid/live-mode refusal,
receipt/source tampering and no side effects from inspection. Early startup
failure with no capture/locks cannot be finalized by this path; retain the consumed
control and observations for manual reconciliation. Hard parent/host failure can
bypass finalization entirely. There is no automatic recovery or hidden retry.

## Kali acceptance

`check_orchestration.py --output-directory NEW_PRIVATE_PATH` requires real Docker
and Unix IPC by default. It first runs 314 core and 13 orchestration tests; unit
integration uses local Node and a pipe. Then it runs these complete scenarios:

| Scenario | Expected final evidence | Disposable containers |
| --- | --- | --- |
| Normal retirement and confirmed direct restoration | Complete/replayed; no reconciliation required | 3 removed |
| Failed unsubscribe, confirmed upstream abort and direct restoration | Complete/replayed evidence of the cleanup failure | 3 removed |
| Broker terminated during the durable shared-shutdown step | Quarantined; shutdown intent pending; no direct restoration | 2 removed |

All eight containers and every attached/worker process must be removed/reaped.
The interrupted case terminates the actual synthetic broker after research
retirement; it preserves the resulting pending handoff intent. Previous SIGKILL
capture/SQLite tests remain accepted separate evidence and are not relabeled as
new Docker tests. All upstream data remain synthetic. Container network, mount,
identity, resource and ownership controls are the accepted fixed controls.

The explicit development flag `--host-pipe-only` uses local Node and pipe transport
with simulated restart policies. Its status is
`offline-orchestration-development-passed-docker-unix-pending`, never Docker/Unix
acceptance. Kali must return `offline-orchestration-passed-live-blocked` and report
eight removed containers. The stable control reuse attempt must be refused for
every case without modifying evidence.

Upload `report.json`, `normal-evidence.zip`, `cleanup-failure-evidence.zip` and
`shutdown-interruption-evidence.zip`. The report retains admission/completion and
cleanup bindings; the existing preservation format retains contract, lifecycle
and capture/journal evidence. Keep the report with its archives. No remote upload,
B2 transfer, retention changes, production restart or wallet action is requested.

## Remaining phase boundaries

Kali acceptance of this combined path is next. Actual production admission and
handoff authorization, remote finalization/retention coverage, reviewed numeric
exposure and live provider validation remain open. This offline wrapper does not
close them. The full R1 gate, measurement pilot and later confirmation study remain
distinct. No ML fitting or profitability claim follows from these tests. Full-gate
Kali validation precedes PR/CI consolidation and an owner-approved merge. The total
five-working-day R1 engineering effort cap is unchanged, not restarted.
