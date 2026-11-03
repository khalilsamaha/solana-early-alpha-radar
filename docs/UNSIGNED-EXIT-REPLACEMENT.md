# Preserve history when replacing an unsigned exit preparation

## Host evidence and scope

The November 3 inspection at 06:44:29 UTC passed all eleven host cases and replayed
an expired collected preparation with no signing record, no backend markers and
no STOP. It confirms 998 acquired atomic units and a 25,000-lamport fee commitment
remain held; the original entry paid 5,000 lamports. The prepared record had only
1,519 ms between persistence and its original expiry. That does not identify the
precise earlier validation failure, but it establishes a narrow timing margin.

This increment implements the internal replacement contract and bounded collector
connection. The supplied CLI is **offline only**. It does not change the user's
saved preparation, access the rehearsal wallet, call devnet, sign or send.
Operational replacement plus signing is the next integration, not a command in
this release. The production scanner, observer and study are unchanged.

## Contract

- The original `admission_exit_preparation` row stays immutable. One separate
  `admission_exit_replacement` row links the original hash to a fully replayable
  collected replacement. No DELETE, UPDATE, deadline extension or reservation
  release is used to make the position appear vacant.
- The caller must opt in explicitly and identify the original hash. The original
  must be expired and collected, the entry must remain settled/open, and the
  source/admission identities must agree. STOP, unknown schemas, signer markers
  (including dangling symlinks), signing or any later-stage table block the path.
- Collection uses the existing twenty-request devnet sequence. Admission identity
  and unsigned eligibility are checked before and after collection, and again
  under the write transaction. There is no automatic retry.
- Replacement observations must start after the original expiry. Full quote,
  account, deployment, simulation and request-provenance checks still apply. A
  distinct recent blockhash is required; pool context cannot regress. Quantity,
  entry identity, held fees and attempt accounting are unchanged. Protected
  inventory cannot decrease and the fee cap cannot increase.
- The replacement keeps its own original collection deadline. Expiry, STOP,
  storage failure or a signer marker before commit rolls back the entire append.
  A second replacement is refused before network access, even after the first
  replacement expires. This is a deliberately bounded first replacement contract.
- Current preparation readers validate **both** records and their relationship.
  Corruption cannot silently fall back to the original. Existing signer requests
  bind the replacement hash and deadline; preparation remains unsigned here.
- Snapshot verification replays both generations and records both hashes. Later
  signing evidence cannot precede replacement persistence. Historical replay
  remains possible after expiry and under STOP without enabling execution.

The append adds no fee, signature or transaction attempt. Real fee accounting
continues to depend on reconciled receipts, never on the existence of preparation.

## Validation

All 54 targeted local tests passed across replacement, legacy preparation,
collection, signing handoff, inspection and source/restore suites. The updated
full-source restore case was also rerun separately: both generations survived
isolated restore, and a rehashed corruption of the original was rejected. The
portable check contains seventeen cases. Two partition checks, source hygiene
and immutable package-manifest checks passed. No real network was used.

Host validation is pending. No live replacement, signing or fee consumption has
been performed by this increment. Local correctness does not establish adequate
live timing headroom.

## Offline Kali check

From the production project directory after fetching the pinned development commit:

```bash
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/unsigned_exit_replacement_cli.py" \
  --output "$PWD/radar-unsigned-exit-replacement-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, seventeen portable cases. Upload only the public
report. No Docker rebuild, service restart or private-journal modification is
required. Do not retry the existing `exit` action or delete any saved evidence.

## Remaining integration

Connect explicit replacement, restricted signing and one-send transport into a
single bounded attempt, with exact preparation identity and the original expiry
carried through every stage. Verify interrupted persistence, lost signer replies,
unknown transport outcomes and recovery without another send. Measure the whole
path before offering the controlled devnet command. The observed 1.519-second
margin must not be treated as adequate just because offline correctness passes.

Then complete devnet exit receipt reconciliation and scoped closure. Economic
qualification and any mainnet pilot decision remain separate gates.
