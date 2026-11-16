# R1 corrective engineering and next host input — 16 November 2026

## Current R1.A/B disposition: omitted Docker field identified and repaired

The next supplied Kali report at `b4f0d7e1` ran November 16,
08:47:20.374329–08:47:20.449588 UTC (09:47:20 CET). Its archive SHA-256 is
`b40e5d0efa9af08419bc4b7f6e1a3c55543ad2c830bb84c3e274cc7555c020a7`.
All fourteen fingerprints match that revision; the separately uploaded JSON is
byte-identical to the ZIP member. Source hashing and the local Docker path check
completed. The first configuration request failed with
`docker-template-field-unavailable-StopSignal`. Every subsequent observation stage
was not-run. No coherent configuration, census, process or capacity observation
was retained. This identifies the current checker failure; it does not retroactively
prove the cause of the earlier generic error or show that the scanner is unhealthy.

The readiness template incorrectly required optional Docker fields through dotted
lookup. It now uses indexed lookup for every allowlisted optional Config and
HostConfig leaf, and handles omitted/empty labels and mounts. This includes
StopSignal and StopTimeout together. Required parent objects and exact identity
remain required. No whole Config/HostConfig dump or additional Docker request is
introduced. Missing stop signal/timeout values stay explicitly unconfirmed; no
effective default or shutdown adequacy is inferred. Secret values stay in local
memory and the existing output/deadline limits are retained.

Implementation review used Docker CLI's
[typed-to-raw inspect fallback](https://github.com/docker/cli/blob/v28.0.0/cli/command/inspect/inspector.go)
and Go's [map-index implementation](https://github.com/golang/go/blob/go1.23.0/src/text/template/funcs.go).
Those establish the template mechanism, not the installed Kali version. Local
validation: **47 production-review tests passed**, including null optional fields,
explicit stop settings, malformed lists, required identity and unconfirmed-setting
findings, plus prior diagnostic/redaction/cleanup cases. Source hygiene passed.
Docker and a Go compiler are unavailable in the reviewer workspace, so the actual
Docker formatter has **not** been executed locally; mocked JSON projection tests
are not claimed as formatter or host acceptance.

**Required next input:** one read-only invocation of
`scripts/r1-production-readiness-kali.sh` at the newly published repair, from a
fresh private `source` checkout. Return `results/production-readiness.zip` even on
exit 1, without repeating or changing permissions. This is justified by the exact
observed StopSignal failure and changed optional-field handling. Its scope and
eleven-request ceiling are unchanged from the diagnostic check below. On a
coherent result, review the actual deployment inputs before advancing R1.A; on a
failure, retain the named stage and not-run paths. R1.B remains partial pending
the deployment inputs. No production change, provider/RPC request, funding,
signing, journal write, E0 observation or confirmation clock is introduced.

## Previous R1.A/B diagnostic repair and its host request

The owner adopted the gate-map v1 and authorized continuation/publication on
November 16. R1.A (deployment inputs) remains blocked; R1.B (production candidate)
remains partial. This repair does not complete either gate or reopen accepted
B0/B1, H1, C1 or native/component acceptance.

The supplied readiness attempt at `dd31e745` ran November 16,
05:34:21.958609–05:34:22.031502 UTC (06:34:21–06:34:22 CET). Its archive SHA-256 is
`b2bc5283c2571ba805599272167bcea1011f22ff2f8e88d1aae15e36783a5339`.
The standalone report is byte-identical to its ZIP member, and all twelve source
fingerprints matched. The result is `deployment-inputs-unavailable`, with no
retained observation. No current production configuration or host root cause can
be inferred from that report. This is supplied evidence, not reviewer host access.

**Diagnosed code defect:** the readiness entry point discarded every exception's
stage and category. It was therefore impossible to distinguish a Docker request
failure, malformed metadata, inaccessible process information or drift. The
repair retains a fixed stage ledger, safe allowlisted error codes, and source-file
line numbers. Later stages remain explicitly not-run. No partial configuration
is promoted to a coherent observation, and failed reports still return nonzero.
Missing optional filesystem facts remain unavailable inside an otherwise coherent
observation; a completed collection stage is not an adequacy/activation pass.

The two readiness configuration requests and two all-container censuses now drain
bounded stderr in memory and publish only a constant diagnostic category, including
a missing template field only when it matches the fixed source-owned allowlist. They
retain the same trusted local endpoint, empty client configuration, read-only
request shapes, four-second command deadline and 16 KiB stdout ceiling; stderr
has a separate 4 KiB ceiling. No raw stderr, exception message, traceback locals,
credentials or arbitrary command values are exported. A CLI diagnostic category
is a clue, not proof of the underlying cause. The accepted context/identity
collector and its request semantics are unchanged.

Local validation: 42 production-review tests passed, including every collection
stage failing in turn, source/config/process drift, secret-bearing exceptions,
private failed archives, and actual disposable subprocess output-limit/timeout/
cleanup cases. These run without Docker, Kali or provider access. Source hygiene
also passed. Historical accepted results are not relabelled with the new source
hashes, and the original failed artifact remains intact.

**One changed Kali check is now needed:** run
`scripts/r1-production-readiness-kali.sh` once from the newly published pinned
checkout named `source`, under a fresh private review directory. It runs no unit
suite, creates no containers, and performs at most eleven read-only Docker
requests (four seconds each, plus bounded child cleanup), with the existing
bounded process reads and metadata-only storage observations. Only private review
files and a temporary empty Docker client directory are written. Do not use sudo,
change permissions, restart services, rerun on failure, or delete old results.
Return `results/production-readiness.zip` even when the command exits 1.

The purpose is to obtain the missing coherent inputs **or identify the actual
failed stage/category on Kali**. A diagnostic failure answers that narrower
question but does not pass R1.A. After review, either use the verified inputs for
R1.B, or fix the identified specific dependency; any further host request must
name that change. No unchanged image/native rehearsal, deployment, signing,
funding, journal mutation, provider/RPC request or E0 observation is included.
Full phase consolidation/PR/CI remains after applicable acceptance. Prior effort
is still unquantified; this record neither invents nor resets the historical cap.

## Earlier corrective batch and accepted context

The owner requested an end to fragmented test/publication cycles and directed
work toward a bounded real-world measurement pilot. This corrective batch is
based on `9c2f59f` on `research/r1-offline-capture-20261111`. It does not declare
R1 complete, activate a provider or deploy the scanner.

## Accepted input

The supplied `production-context.zip` has SHA-256
`fbc2bf227582038dc891ef8d1d02451363e9652e98242b93ae0d7b061816d55c`.
At source `9c2f59f`, its nine source fingerprints, canonical metadata fingerprint
and sixteen passing tests agree. The observation ran November 16,
04:59:32.090047–04:59:32.520984 UTC (05:59:32 CET). It records the existing scanner
running and healthy, with one project-labelled container. This is supplied host
evidence, not reviewer access to Kali or a current health claim. That accepted
context check needs no repeat.

## Engineering completed

- A stopped connection owner refuses to start. STOP/peer loss during connection
  opening aborts a late-returning wire before subscriptions. Previously, the
  early `closed` guard in `abort()` could leave that wire open.
- Session startup has one configurable deadline covering endpoint, peer,
  admission, capture startup and connection opening. STOP interrupts these
  waits; cancelled startup joins the capture worker and publishes no completion
  receipt. The capture lease wait follows the setup/shutdown allowance instead
  of a separate hard-coded ten seconds. An explicit server factory permits
  integration without globally replacing the Server class.
- `r1-integration/session_evidence.py` exports arbitrary separated-session
  captures, journals and receipts. It replays copies, reconciles upstream
  commands with journal records, binds retirement to final shutdown, and
  preserves interrupted/rollback bytes without repairing them. Clean, failed
  and quarantined outcomes are distinct. The exporter has no synthetic-upstream
  or fixed four-row requirement.

The exporter is local evidence handling, not a production launcher or remote
retention system. Provider origin, full handoff, billing cutoff, precollection
approval and remote retention are not established by an archive. Active session
or capture locks refuse export. Historical evidence still needs its recorded
source revision; changed source fingerprints must not relabel old receipts.

Targeted local validation: 138 tests passed across owner lifecycle (20), session
and archive compatibility (27), combined integration (26), manifest capture
supervision (13), actual Node pipe integration (12), new startup/export tests
(15), and production metadata/report/readiness tests (25). No provider,
production Docker or Kali observation was performed here. This workspace rejects
Unix sockets and has no Docker. Full consolidation/PR/CI remains after applicable
host acceptance.

## Original input request (superseded by the diagnostic repair above)

Run `scripts/r1-production-readiness-kali.sh` from a fresh pinned checkout named
`source`; return `results/production-readiness.zip`. It runs no unit suite and
creates no test containers. Its bounded read-only pass collects:

- Fixed production identity and configuration fingerprint; recognized command,
  source-mode, hardening and port comparisons; actual named data volume and
  original Compose locations, where available.
- All running Docker container IDs, not just project-labelled containers.
- Metadata-only presence of `/app/.env`; no contents are read.
- Available bytes/inodes on the proposed home-directory storage filesystem and,
  if accessible, the existing `/app/data` mount's host filesystem.

Docker environment values are read locally in memory. Reports contain names,
fixed-value comparisons and an aggregate fingerprint, never raw values, commands
or credentials. No production files, restart policy, container state, permissions
or operational journals change. Review files are the only persistent writes.
There is no provider/RPC request, credential-file load, signing, funding, trading
or deployment. Return an unavailable report rather than rerunning or changing
permissions if the observation fails.

This addresses facts absent from the accepted context report. It does not prove
full effective configuration or global owner exclusivity: host processes and
other machines are outside the Docker census. Filesystem samples are not space
reservations or retention approval. The home filesystem is a proposed input to
the capture layout, not an approved production directory.

## Remaining delivery and its endpoint

| Remaining work | Required result |
| --- | --- |
| Production handoff and rollback | Preserve actual Compose project, volume, configuration and image; establish one shared owner and verified scanner peer; uncertain transitions stay unresolved |
| Finite live worker and credentials | Integrate accepted capture/wire code with reviewed runtime/resources, private credential delivery, STOP, parent-death containment and no reconnect/rearm |
| Durable delivery and pilot terms | Approved destination/retention and numeric duration/resource/data-fee/exposure limits; completed and interrupted evidence survives transfer and independent restore |
| Real measurement pilot | Usable data with a pass/fail/insufficient verdict for completeness, gaps, timing, unresolved records and costs |

The requested host input permits deployment-specific work against the actual
setup. It does not mean these remaining items are implemented or only paperwork
remains. Combine remaining changed-boundary acceptance; do not request unchanged
image/control/native rehearsals or start another parallel framework.

Standing publication authorization covers this research branch. The November 16
instruction authorizes this corrective work; it supplies no numeric provider
budget or deployment approval. Historical focused effort remains unquantified;
no remaining allowance or reset of the five-day cap is claimed. No live pilot or
confirmation window has started; November 19 is not a substantiated start date.

E0 remains independent and blocked with holds preserved. Its last accepted
operational observation remains November 9, 18:50:41 CET. On November 20, absent
required closure evidence, retain that disposition and reopen only for material
exact receipt/history evidence or a specific journal discrepancy enabling scoped
reconciliation. This work obtains no E0 observation or current balances.
