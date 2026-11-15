# R1 native offline handoff — 15 November 2026

## Implementation and scope

The accepted exact-target control proof now connects to the handoff coordinator
through native Docker/Unix adapters. The increment is additive; accepted control,
coordinator and image packages are unchanged. The host batch reuses the accepted
image `sha256:8c6e3458333f587cb1a5110dbfdc2d6c98f2bdcc6892eb589ee08cf8b9b66140`.
It performs no build, pull, production control, credential read, provider request
or remote-storage operation.

Each adapter checks the retained coordinator intent and operation identity before
dispatch. A separate immutable plan binds source hashes, claim and fault scenario.
The original inert direct actor must remain stopped. The image-contained scanner
shared-discovery adapter consumes synthetic events from a bounded Python owner;
no scanner loops or real upstream transport are started. Exact command, image,
isolation, container generation, socket inode, Unix credentials and peer process
identity are checked. Restoration requires the original target still stopped,
owner reaped and consumer stopped, then reproduces the original configuration and
restart policy in a new inert actor.

Clean research retirement is followed by another discovery event. Failed cleanup
closes the stream and retains its failure. Deliberately lost responses occur after
the action and its evidence checks; fixture disposal cannot confirm pending work.
Recovery reads preserve the journal bytes and never automatically resume.

## Development evidence

Final development batch: 15 November, 10:13:35–10:13:38 CET. All 48 tests passed
(11 native adapter, 20 coordinator, 17 control); zero failures, errors or skips.
All five process scenarios completed with clean captured diagnostics and child
cleanup. The Python/Node children and scanner adapter are real local processes;
transport is a pipe and Docker observations are simulated. Result:
`native-handoff-development-passed-docker-pending`.

| Scenario | Expected retained disposition | Restored actors | Total actors |
| --- | --- | ---: | ---: |
| Normal | Rolled back; research unsubscribed | 1 | 3 |
| Cleanup failure | Rolled back; upstream-aborted retained | 1 | 3 |
| Lost owner-start response | Pending start_owner; no restoration | 0 | 2 |
| Lost shared-stop response | Pending stop_shared; no restoration | 0 | 2 |
| Lost restore response | Pending restore_direct; created actor unconfirmed | 1 | 3 |

The last scenario removes its restored fixture during disposal without changing
the pending journal. None of these cases verifies production/provider ownership,
billing cutoff or E0 state. No native Docker/Unix acceptance is claimed locally.

## One consolidated Kali acceptance

Use a clean pinned checkout named `source` beneath a new private review directory.
Run `bash scripts/r1-native-handoff-kali.sh` once. The wrapper creates sibling
`results` and returns `results/acceptance.zip`, including reports, validation log,
plans, exact control proofs, coordinator claims and journals. It refuses an
existing results directory. Keep failed evidence and do not rearm or retry it.

The native runner requires the existing local Docker socket, UID/GID 1000 and
accepted image. Missing prerequisites stop without installation, permission
changes or development-mode fallback. Native acceptance requires all 48 tests,
all five scenarios, exact source hashes, thirteen owned containers removed,
reaped children and the expected pending states above. Expected aggregate status:
`native-handoff-offline-passed-live-blocked`. Return the bundle even on failure.

Private consumed registries remain at their recorded short `/tmp/r1nh-*` paths;
the archive retains their claims and journals for historical review. Do not move
or reuse them as live registries. No earlier unchanged image/control batch needs
repeating, and no real B2 transfer is requested.

## Remaining R1 completion requirements

This closes the current adapter implementation increment, subject to native host
acceptance. Full R1 readiness still requires actual scanner/owner configuration
and global connection exclusivity, production admission/rollback and provider
close evidence, live credentials and supervision, real variable-session delivery,
capacity/retention evidence and approved numeric pilot terms. The current broker
is deliberately synthetic and cannot supply those results.

After the returned native evidence is reviewed, reconcile the remaining scope
against the unchanged total five-working-day engineering cap before extending
implementation. No reliable remaining-effort balance is available. November 19
is unconfirmed; no pilot or 21-complete-UTC-day study clock has started. December
31 remains a scope/verdict checkpoint. E0 remains independently held with its
November 20 evidence checkpoint and November 9 last accepted operational observation.
