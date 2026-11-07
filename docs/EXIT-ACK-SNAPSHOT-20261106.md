# Exit acknowledgment within a read snapshot

## November 6 evidence and decision

The Kali inspection at 06:32:01 UTC was `continuation-eligible-research-only`.
Original and replacement identities matched. The owned quantity remained 998,
protected inventory 500000000, remaining fee commitment 25000 lamports and
per-attempt fee cap 10000 lamports. No state or reservation was changed.

The observation at 06:32:11 UTC completed all twenty fixed devnet requests,
including unsigned simulation. Collection took 6972 ms within its original
freshness interval; validation took 643 ms, leaving 2385 ms. The diagnostic's
broader collection timer was 9905.341 ms and includes admission work before
that freshness interval. These clocks must not be substituted for one another.
There was no signing, sending, preparation append or reservation release.

This passes inspection and observation, not end-to-end timing qualification.
The earlier offline signing phase alone took 2977.638 ms on Kali. Different
runs cannot establish an exact combined budget, but this is enough reason to
reduce avoidable local work before consuming the one continuation slot.

## Change

Before each of the two transport preflight boundaries, the transport already
replayed signing state inside a consistent read-only transaction. Its backend
acknowledgment check then replayed the same preparation history again.

The transport now checks the acknowledgment against that same snapshot's
validated signing state. The internal helper requires a read-only transaction.
It still reads and checks the attempt marker, signing boundary hash and time,
acknowledgment file, request identity, wire hash, signature and message binding.
No mutable state or authorization decision is cached. Standalone backend calls
and recovery still perform their own full signing-state replay.

The transaction ends before any RPC. A fresh read-only transaction performs all
checks again after provider preflight, before committing the durable send marker.
Source checks, STOP, clocks, fee limits, one-send behavior and independent signer
validation remain enforced. Recovery still rereads evidence after writes and RPC.

## Validation and host use

Use the existing `position-book/continuation_exit_cli.py --large-fixture`
offline rehearsal. Its submission phase reports `preservedGenerationReads`;
the expected count falls from ten to eight. Real network latency is not simulated
by this count or by the rehearsal's wall clock. Host timing must be measured.

Targeted tests cover transaction enforcement, acknowledgment-file changes within
a snapshot, release of the read transaction before RPC, signing and acknowledgment
changes during RPC, standalone replay, concurrent writers and recovery behavior.
The complete submission and independent-backend regression suites and connected
continuation rehearsal remain required before publishing this increment.

Local validation completed: ten snapshot tests, sixteen submission/backend tests
(including their 24-case transport and 27-case restricted-signer CLI checks),
two partition checks, and source hygiene passed. The adjusted standalone-replay
test was rerun after its final test-only edit. The connected 1 MiB rehearsal
passed all sixteen integration/fault and fourteen independent contract cases.
Submission performed eight preserved-generation reads, down from ten. This run
took 4118.867 ms overall, with 6702 ms deadline headroom; submission took
1289.538 ms. These local results do not predict Kali or live-network timing.

PR #78 remains unmerged: GitHub did not start its jobs because the account has a
payment/spending-limit restriction (user-supplied Actions annotation). This is not
a passing CI run. No workflow, required check, deadline or account billing setting
is changed here. This increment is committed separately under the agreed batched
workflow; it does not deploy the scanner or consume the devnet continuation slot.
