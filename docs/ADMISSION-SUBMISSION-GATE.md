# Admission submission and receipt collection — 30 October 2026

## Accepted input and scope

The restricted-signer host report captured at 2026-10-30 18:38:34 UTC exactly
matched the 19-case local self-check. It created one disposable signature from
two temporary test keys, made zero network requests and sent zero transactions.
No production wallet was accessed. That accepts the host signing mechanics.

This release is the third development increment after PR #63: receipt binding,
restricted signer, then submission and receipt collection. It is not a deployment,
third-cycle approval or mainnet release. The scanner, observer, alerts, production
services and fixed study are unchanged. The host check below is offline only. Its October 30 19:10:35 UTC report matched
all 18 expected cases and flags exactly; the host gate is accepted.

## New internal integration

`position-book/admission_submission.py` connects the existing signed admission to
a fixed devnet RPC transport. The `submit()` API requires the exact boolean
`allow_devnet_submit=True`; no execution CLI, service or scanner calls it. The
`opener` seam exists for deterministic transport testing. Runtime use of a custom
transport is outside the fixed-endpoint trust assumption.

The cooperating source lock covers the entire operation. It opens the existing
fixed sibling admission ledger and checks the wallet/pool scope, saved exact
signature acknowledgment and accounting handoff. It does not create a new
allocation or refresh the original deadline. Previously imported receipts block
a new send attempt.

Before recording the send boundary, it performs at most four RPC requests:

1. Confirm the expected devnet genesis hash.
2. Check the original blockhash at confirmed commitment.
3. Check the fee for the exact signed message, with a context at least as recent
   as the blockhash observation, within the already reserved entry cap.
4. Check genesis again and recheck STOP plus the original deadline.

It then commits a private `admission_submission` record in the **same admission
SQLite database**, using its existing FULL-synchronous transaction policy. The
record binds the admission head, handoff, signature, exact wire hash, endpoint,
preflight evidence and time. Only after the commit can one `sendTransaction`
request occur. It uses the exact saved wire, `skipPreflight=false`, confirmed
preflight commitment, `maxRetries=0` and the observed minimum context slot.

There is no application retry. A timeout, malformed response, process interruption,
or failure while saving the response leaves the existing attempt unresolved.
Re-entering `submit()` returns its stored status with zero network calls. A wrong
returned signature quarantines the attempt. An RPC acknowledgment is not a fill.
A boundary may exist even if the process died before making the request: its
meaning is "sending may have happened", never proof of delivery.

This adds fresh blockhash/fee checks and RPC preflight, not a second complete pool,
program or wallet-state observation. Those raw checks belong to the original
fresh admission. Its deadline is never extended. Other senders or copied source
directories are outside this per-directory concurrency model.

## Receipt collection and recovery

`recover()` has a separate read-only RPC allowlist. It cannot call sendTransaction,
resign or replace a plan. It may write local evidence, so it is not a read-only
filesystem operation. After expiry or STOP, it can still observe existing effects.

Each collection is bounded to four fixed-endpoint requests: genesis, the recorded
signature status, the finalized base64 transaction, and genesis again. Responses
have byte limits and redirects/proxy inheritance are disabled by the existing
transport. There is no polling loop or automatic retry. At most eight captures
are retained for this admission; hitting the cap refuses another collection and
preserves uncertainty rather than deleting evidence or claiming a failure.

The collector checks both genesis observations, exact signed transaction bytes,
version and a receipt slot no older than the pre-send blockhash observation. It
normalizes the decoded message and retains bounded RPC metadata. The existing
receipt gate then checks finalized status, signature/message, exact admitted pool
vault movements, token effects, fees and native balance conservation.

Recovery recognizes package identities already validated in the receipt inbox;
it does not repeatedly append earlier unknown observations.

Captures form a bounded hash-linked sequence tied to the send boundary in the same
SQLite file. A capture is committed before receipt application. If the process
stops between those steps, recovery replays the stored capture without RPC. A
terminal receipt is replayed on subsequent recoveries without new requests.
Wrong genesis, changed wire and contradictory terminal evidence quarantine.
Missing receipts stay unknown; failed finalized receipts remain fee-only outcomes.

`genesisBoundReceiptCollected` means consistent evidence collected through this
local fixed-endpoint workflow. It is **not cryptographic authentication of RPC
metadata, proof of wallet-wide solvency, or a released allocation**. Public
reports expose summaries rather than signed wire or raw response payloads.

## Verification and host check

The portable self-check uses an existing public synthetic signature fixture,
private temporary ledgers and an in-memory fake RPC transport. It creates no
keys or signatures and makes no real RPC requests or sends. Its 18 cases include
commit-before-send, duplicate refusal, lost response, STOP/expiry recovery, exact
wire/genesis validation, fee refusal, failed receipts, unknown receipts, retained
reservations and capture-to-receipt interruption recovery.

The deeper local tests additionally cover a child process exiting immediately
after the durable boundary, competing callers under the source lock, disk-write
failures, changed journals, oversized records, capture/request caps, clock/scope
mismatches and an actual disposable signer → synthetic transport → receipt path.
These tests establish mechanics, not network delivery or deployment acceptance.
The full position-book regression run passed 363 tests. The final focused suite
passed all 23 tests, including the additional repeated unknown-capture recovery
case and its replay correction. Source hygiene and package manifests also passed.

After fetching the exact commit supplied in chat:

```bash
cd ~/apps/solana-early-alpha-radar
umask 077
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/admission_submission_cli.py" \
  --output "$PWD/radar-admission-submission-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, 18 cases, zero network requests, signatures and
transactions. Upload only that public report. No sudo, rebuild or restart is
needed. The CLI has no execution, wallet, directory or receipt-import arguments.

## Remaining acceptance and integration

1. The synthetic transport host check is accepted. Consolidate this three-increment
   batch with the agreed PR/CI review. A merge does not deploy this path.
2. Authoritative entry/exit accounting and allocation ownership. This release
   deliberately retains all original principal and fee reservations even after
   a consistent receipt. It does not update the production position ledger.
3. Add the sibling admission database, signer attempt and acknowledgment files to
   key-excluded private recovery. Test a restored unresolved send without
   duplicating submission or losing its reserved budgets.
4. Integrate delayed exits, failed exit fees, residual exposure and STOP handling,
   then agree and rehearse a new controlled devnet scope before deployment.
5. Narrow mainnet route controls and an explicitly authorized mechanics pilot
   remain separate from prospective strategy qualification.

The fixed availability study remains untouched. Preserve captures November 1, 3,
5 and 6; review November 6 at 00:05 UTC / 01:05 Europe/Amsterdam.
