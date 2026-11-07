# Independent successor key backend — 7 November 2026

## Accepted prerequisite

The Kali handoff report captured at 18:55:10 UTC passed all 15 cases. It verified
separate durable signing boundaries, exact disposable signatures, lost-response
recovery and preservation of the retired generation. It did not exercise an
independent successor private-key process.

## This increment

The new restricted process reads the committed successor and signing boundary
from the owned private ledger. It independently reconstructs the retired signing
context, verifies the actual old Ed25519 signature and backend markers, checks
both expiry/account proofs, and compiles the exact new reverse message. It binds
attempt two to the original owned quantity, protected inventory, fee commitment
and ten-second collection deadline. The retired fee exposure is retained; the
successor cannot add a reservation, reuse the retired blockhash or increase its
fee cap. The Python caller still performs the complete historical and raw
collection validation; the independent compiler is an additional boundary, not
a replacement for that replay or independent chain finality.

Two new files belong only to this generation:

- `successor-signer-attempt.json`: exclusively created and fsynced before signing.
- `successor-signer-ack.json`: the exact signed wire, durably saved after signing.

The old `exit-signer-*` files are checked and preserved. Any existing new attempt
or acknowledgment prevents another backend invocation from signing. Competing
processes have one exclusive marker winner. A crash after the marker leaves the
attempt unresolved, even if no signature was actually produced. There is no
marker reset, automatic retry, extra reservation or submission in this release.

The internal opt-in adapter uses the existing durable unknown boundary. Keyless
recovery verifies the saved new markers and exact signature before recording the
reply; STOP and expiry do not erase a valid late acknowledgment. Missing or
corrupt files refuse recovery. The snapshot inventory now includes the new files,
and semantic snapshot projection binds them to the successor and signing head.
No signing key is included in a snapshot.

The public CLI exposes **offline checks only**. It accepts neither a wallet nor a
private directory, and it has no execute action. This release does not activate
the backend against the user's wallet or change scanner/observer services.

## Validation

The independent Node suite exercises 41 cases: valid signing, unchanged database,
retired-marker preservation, lost ACK/repeat refusal, concurrent processes,
rehashed proof/request attacks, attempt/fee/quantity/deadline violations, changed
account balances, wrong key, STOP, unsafe file permissions/symlinks, sidecars,
old submission evidence and old-marker conflicts.

Nine Python recovery/adapter cases exercise real retired-source semantic replay with
disposable signed replies: explicit opt-in, keyless late and duplicate recovery,
marker identity/clock checks, missing/conflicting ACKs, snapshot inventory and
semantic binding, orphan/symlink rejection, acknowledgment-write rollback, and committed-boundary/ACK integration with a controlled child-process reply.
The independent process and recovery tests use different synthetic fixtures;
they do not establish the timing of a complete live collection/signing path.

Local verification passed all 50 portable cases (41 independent-process checks
and nine adapter/recovery cases). The original signer’s 27 checks, 12 unsigned
successor regressions, six retirement snapshot regressions, two test-partition
checks and six CLI scope/output refusals also passed. Source hygiene and package
manifests passed.

Host acceptance remains pending. Run the pinned commit and offline command from
chat; upload only its public `radar-successor-key-check-*.json.gz` report. No
Docker rebuild or service restart is required. Keep all existing private journals.

## Finite next integration gate

After host acceptance, connect the complete fresh collection/persistence/key
backend path in a measured rehearsal before prescribing a live attempt. Then
bind one controlled devnet send and exact receipt reconciliation to this generation.
The old sender must remain unable to send the retired wire. Keep all deadlines
unchanged: failure to finish is a failed timing gate, not retry permission.

This is progress on recovering and closing the held devnet position. It does not
establish a profitable entry rule, mainnet route compatibility or funded-pilot
approval. The economic review and closed study decisions remain unchanged.
