# R1 corrective engineering and next host input — 16 November 2026

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

## One Kali input, not another rehearsal

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
