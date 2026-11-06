# Signed exit expiry: preserved evidence and next diagnosis

The November 6 controlled continuation did not pass live execution acceptance.
Collection made 20 RPC requests; one signature and its acknowledgment were
recorded, but the original deadline elapsed before submission began. The report
records zero sender requests and no application send boundary. The subsequent
read-only audit found coherent signed evidence, 998 acquired atomic units still
held, protected inventory of 500000000, and 25000 lamports of fee commitments
held. No scoped closure or release occurred.

The active preparation identity in that report is
`d8ab974e819a953ecf015aa3acee403e8ca30f822bac72e58d92263218f9dd97`.
Its two predecessor preparations remain preserved. The unsigned continuation
slot has been consumed. Do not rerun execution, erase markers, widen the deadline,
or treat signature expiry as permission to release funds or sign a replacement.

## Timing interpretation

Collection diagnostics report 6479.274 ms, including local validation and RPC
work. The stored preparation timestamp precedes validation, serialization and
commit. Subtracting that timestamp from the deadline gives 3398 ms, **not**
measured post-commit signing headroom. The current reports do not identify pure
cryptographic signing time or the time at which the signature was created.
A faster offline rehearsal with synthetic responses did not prove that the live
RPC path would finish within the same ten-second deadline.

## Engineering change

`exit_profile_cli.py --action inspect` now includes `signingTimeline` alongside
the existing per-request collection timing. It validates the saved signing
ledger, backend attempt marker, signed acknowledgment, current preparation
identity and transport state under local read locks. It reports:

- Preparation record timestamp to the durable signing-boundary timestamp.
- Signing boundary to backend attempt-marker timestamp.
- Backend attempt-marker timestamp to acknowledgment-row timestamp.
- Signed deadline headroom at each recorded boundary, including negative values.
- Whether a local application send boundary exists, retaining the distinction
  between locally unsubmitted evidence and a possibly lost transport response.

Commit completion, actual signature creation and acknowledgment-file write
instants were not recorded; these remain null. Reported intervals include
validation, persistence and process work, not just crypto or CPU time. No raw
signed wire, private key, arbitrary error, wallet address or RPC endpoint is
exported by this diagnostic.

The attempt-marker validator was factored to return its already-validated marker
for this diagnostic; ordinary signer and transport validation still call the
same checks. No deadline, retry, admission, collection, signing, sending or
reservation policy changed. Missing/corrupt signing artifacts make the report
unavailable, with no partial success.

No chain queries occur. A missing local send boundary does not prove that a
signed wire was never broadcast elsewhere. Local quote/preparation expiry does
not establish Solana blockhash expiry. This report does not authorize a fourth
generation, resend, re-signing, settlement, release or new position.

## Independent availability study

The existing `availability-study/review.sh` reads saved captures, checks the
fixed registration and maturity boundary, and writes a report. It makes no
network requests, changes no admissions, and neither refits nor activates the
model. It is independent of this devnet failure. Save the scheduled final
capture first if it has not already been captured; do not extend the fixed study
window or change thresholds to force a result.

## Operator step

Use the pinned release commit and run `exit_profile_cli.py --action inspect`
with the existing directory, wallet and pool. This is inspection only and needs
no signing/submission flags or Docker rebuild. Preserve all source journals and
upload the public timing report. The next implementation decision follows those
actual saved timings; a safe expiry refusal is not a completed exit.

## Local validation

- Four new signed-timing regression tests, including late signed acknowledgment,
  lost-send-response distinction, missing/corrupt backend files, and corrupted
  signing ledger. Public fixtures only; network and private signer calls blocked.
- Ten existing exit-profile tests, including the connected disposable-key
  rehearsal, persisted-expiry reproduction, unsigned historical timing and CLI
  output guards.
- Four existing restricted-signer tests, including its offline contract checks,
  actual independent backend with disposable keys, and keyless recovery.
- Source hygiene and two CI-partition coverage checks.

These checks validate the diagnostic and preserve existing signer behavior.
They do not prove that the live execution deadline can be met. GitHub-hosted
CI and consolidation remain separate from local validation; this increment
does not bypass PR #78's blocked checks or merge that PR.
