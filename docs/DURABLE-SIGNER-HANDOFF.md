# Durable signer-adapter and accounting handoff — 30 October 2026

## Starting evidence

The host `locked-admission-binding-1-self-check` captured at
2026-10-30 11:34:06 UTC matched the expected report exactly apart from capture time:
17 cases, temporary ledgers removed, zero RPC requests, signatures and sends.
This accepts the prior synthetic checkpoint, not a live source or signer run.

This third development increment completes the current batch's adapter contract.
Local tests precede a pinned Kali self-check; consolidate the batch after host
acceptance and the normal PR/CI checks. PR #62 remains the merged base.

## Implemented behavior

`signer_handoff.dispatch()` requires an explicitly supplied, trusted in-process
adapter. There is no default signer, private-key implementation, production
installation, transaction sender or live CLI action in this release.

The dispatcher holds the existing cooperating wallet lock from source validation
through acknowledgment persistence. It uses one fixed sibling directory,
`<source-directory>-entry-handoff-v1`, and one `entry.admission.sqlite` file.
Callers cannot choose another allocation filename for this dispatcher. The source
journals remain read-only. The dispatcher's separate ledger is private and writable.

The durable sequence is:

1. Replay the controlled source and validate private raw market, message, deployment,
   fee, simulation and balance evidence. Commit principal and all exit-attempt fees.
2. Save the exact unsigned request and a receipt-intent template derived from the
   original raw wallet/token balances and mint decimals. No later price or balance
   replaces that template.
3. Replay the source again, check the stop marker and original deadline, and commit
   the signing-unknown boundary before invoking the adapter.
4. Recheck the supported instruction contract and expiry. Invoke the supplied
   adapter once while retaining the wallet lock. The adapter receives a detached
   copy of the exact bounded request.
5. Verify its existing signed response against the reserved message and wallet.
   Persist it, then stage a private accounting handoff in the **same ledger**.

The accounting handoff contains a deterministic identity, the signed receipt intent
and the existing principal/fee commitments. Its private reader supplies the exact
signed wire for a future accounting consumer. Public reports exclude the wire,
request body, receipt template and private handoff body.

The outbox is a record awaiting later accounting integration. It is not a second
budget, an applied receipt or a submission permit. No reservation is released.

## Recovery and refusal rules

| Event | Result |
| --- | --- |
| Source, raw funding or policy check fails | Adapter is not called |
| Request/boundary write fails | Adapter is not called; any committed reservation remains held |
| Process dies or adapter raises after the boundary | Signing-unknown survives; repeated dispatch does not call the adapter |
| Valid response exists after a lost acknowledgment | Recovery verifies and records it without invoking a signer |
| Response was saved but the accounting write failed | Recovery stages the handoff from saved evidence |
| Evidence expires during the call | Existing signed evidence is retained; no freshness/submission approval |
| Stop arrives before or during the call | New invocation is blocked when observed before it; a returned response is retained in stopped state |
| Conflicting or invalid signature | Quarantine; no accounting handoff or budget release |
| Same response/handoff is recovered repeatedly | Stable identity, no new allocation or duplicate event |
| Missing or unsafe fixed ledger | Recovery refuses; it never creates a replacement allocation |
| Legacy prototype lacks a saved request | No receipt template is invented after signing |

`recover()` has no signer argument and does not replay old source receipts as a
reason to re-sign. It reads wallet metadata under the source lock and may write the
separate admission ledger. It is not a read-only operation on that ledger.

## Validation and host check

The portable check uses a synthetic adapter returning a previously generated
public signature fixture. It creates no signatures and accesses no private key.
Its 15 cases cover committed ordering, lock ownership, one-call behavior, expiry,
stop, conflicting acknowledgments, write failures, recovery and private output.

The focused test suite additionally kills subprocesses, exercises unsafe paths,
rejects changed policies and oversized state, and proves consumer compatibility:
the existing position book accepts the private handoff and reconciles a synthetic
finalized receipt in a disposable ledger. That compatibility test is not a
production transfer between two accounting systems or evidence of a real fill.

Local validation passed: 311 position-book regression tests, an additional
real-source observer-to-dispatch integration test, 52 token-reconciliation tests,
source hygiene and package manifests. The focused dispatcher suite contains 19
tests already included in the position-book run. The host report captured at 2026-10-30 13:30:54 UTC matched all 15 cases and every safety flag exactly. No live signing or submission was exercised.

After checking out the pinned commit supplied with this release, run:

```bash
cd ~/apps/solana-early-alpha-radar
umask 077
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/signer_handoff_cli.py" \
  --output "$PWD/radar-signer-handoff-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, **15 cases**, zero network requests, signatures
and transactions. Upload the public `.json.gz` report. No sudo, Docker rebuild,
service restart, wallet path, live signer or execution argument is required.

## Remaining gates

- Connect a narrowly scoped private-key backend with its own durable one-shot
  acknowledgment protection. This release validates the adapter contract only.
- Implement the authoritative submission/receipt transition and allocation
  ownership without making the admission and position books independently spendable.
- Rehearse unknown submissions, actual failed receipts, delayed exits and remaining
  fee commitments before opening another controlled devnet scope.
- The fixed sibling ledger is per canonical source directory, **not wallet-wide**.
  Source copies/renames, unrelated senders, external wallet activity and separately
  created prototype ledgers are outside its ownership control. Do not deploy it
  as a general portfolio manager or use it as permission for another cycle.

Scanner, quote observer, alerts, backups, completed devnet cycles and the fixed
availability study are unchanged. Preserve November 1, 3, 5 and 6 captures; review
November 6 at 00:05 UTC / 01:05 Europe/Amsterdam. No strategy, mainnet route or
real-money pilot is enabled by this engineering checkpoint.
