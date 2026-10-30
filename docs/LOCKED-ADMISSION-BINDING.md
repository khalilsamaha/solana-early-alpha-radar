# Locked source admission and signed acknowledgment — 30 October 2026

Host acceptance: the October 30 11:34:06 UTC report matched all 17 cases exactly,
excluding capture time. The next [durable adapter handoff](DURABLE-SIGNER-HANDOFF.md)
adds one-call dispatch and a same-ledger accounting record. The production key
backend and receipt application are still disabled.

## Accepted starting point

The 15-case `pre-sign-admission-1-self-check` host report captured on October 30
at 10:22:25 UTC exactly matched the local portable result, excluding capture time.
That accepted the standalone reservation prototype; it did not exercise a live
signer. PR #62 remains the consolidated base. This is the second development
increment in the next local-test-first batch, with consolidation still pending.

## What this increment connects

`position-book/locked_admission.py` connects the existing controlled source reader
to the separate private admission ledger:

1. Acquire the existing cooperating wallet lock without opening the private key.
2. Open source journal connections read-only and replay the closed two-cycle
   evidence. Compare wallet, pool, held balances, account roles, ledger head and
   cycle identity against the private raw observation.
3. Recompute the raw quote, deployment, simulation effects, exact unsigned message
   and principal/fee allowance, then commit the reservation atomically.
4. Replay source evidence independently after reservation. Recheck identity,
   ordered clocks and the stop marker before committing the signing-unknown
   boundary. Revalidate the original raw evidence and deadline at that boundary.

A stop arriving during final raw validation is recorded before a successful
handoff can return, while retaining the boundary and budget. If the second read
fails, the first committed reservation remains held. If the
first read fails, no reservation is added. Repeating a call cannot create a second
signing boundary or refresh evidence. The adapter refuses an admission file inside
the controlled source directory.

The observer's cost calculation can finish before its evidence handoff. Admission
now accepts ordered calculation/completion timestamps rather than requiring them
to be identical. All original observation, blockhash and quote expiry checks remain
in force; no timestamp or deadline is extended.

## Exact signed response and recovery

`Admission.record_signed()` accepts an already existing, bounded signed wire. It
uses the existing Ed25519 verifier and requires one signature from the scoped
wallet over the exact reserved message bytes. It does not request a signature.
The signed wire stays in the private admission ledger; public summaries omit it.

| Condition | Durable result |
| --- | --- |
| No recorded signing boundary | Reject the acknowledgment |
| Missing acknowledgment or verifier interruption | Preserve signing-unknown and the held budget |
| Correct signed message | Record its signature and wire/message identity, keep the allocation held |
| Same acknowledgment repeated or process restarted | Return the existing state without another event or signature |
| Expired evidence but a correct existing signature | Record the evidence; grant no freshness or submission permission |
| Stop requested before acknowledgment | Record a valid response but remain stopped |
| Malformed, invalid or differently signed message | Quarantine the allocation; do not release funds |
| Later correct response or stop after quarantine | Keep quarantine; no automatic repair |

Recording recovery writes the separate admission ledger. It is not a read-only
operation on that ledger, but it does not modify the controlled source journals,
use RPC, re-sign or submit. A failed ledger write preserves the prior uncertainty.

## Validation

The portable check covers 17 scenarios with temporary ledgers, a real file lock,
synthetic source snapshots and an existing public signature fixture. Its reported
signature count is zero: it verifies fixture signatures but creates none. The
fixture's disposable private key was never saved. It is not a chain transaction.

Local integration tests additionally replay the actual synthetic two-cycle
journals and the observer's private evidence handoff through the real parsers.
They compare source files byte-for-byte and cover missing receipt rejection.
Other tests cover verifier failure, atomic write failure, process death after
acknowledgment commit, output permissions and rejection of live CLI flags.

Validation completed locally: the 289-test position-book regression run passed.
After the final verifier/stop refinements, all 32 focused admission tests and
three real source-replay integration tests passed. The 39 intent-journal tests,
source hygiene, package manifests and diff whitespace checks passed as well.
The focused counts overlap the regression suite; they are not extra independent
strategy observations. Host acceptance of this increment remains pending.

Run the host check after checking out the exact reviewed development commit:

```bash
cd ~/apps/solana-early-alpha-radar
umask 077
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/locked_admission_cli.py" \
  --output "$PWD/radar-locked-admission-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, 17 cases, and zero network requests, created
signatures and submitted transactions. Upload that public report. No sudo,
Docker rebuild, service restart, wallet directory or live execution flag is needed.

## Limits and next step

This is an integration prototype, not a new live spending system. The source
witness is a point-in-time observation under a cooperating lock. It does not
control external wallet activity or prevent separate, independently created
admission ledgers from overcommitting the same funds. The private admission ledger
is not yet consumed by the controlled sender or wallet-wide accounting. Its state
cannot be used as a standalone signing capability after the source lock is released.

Next: design and test the restricted signer invocation and durable handoff to
receipt accounting, keeping a single authoritative allocation and the lock across
that boundary. Rehearse a lost acknowledgment without ever issuing a second
signature automatically. Then consolidate the batch after host acceptance and CI.
No third controlled cycle or mainnet execution is enabled here.

The scanner, quote observer, notifications, backups and fixed availability study
are untouched. Preserve captures on November 1, 3, 5 and 6; review November 6 at
00:05 UTC / 01:05 Europe/Amsterdam. Successful mechanics checks do not establish
profitable selection or authorize a real-money pilot.
