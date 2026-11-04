# Bounded unsigned exit continuation — 4 November 2026

## Accepted host evidence

`radar-history-reuse-check-20261104T182231Z-2478410.json.gz` passed at
18:24:18 UTC. Archive SHA-256:
`c1c1bf421ac478057bdb55caa1967652512285eb348108cde24baa1938e0e1b3`.

The connected synthetic attempt took 4,260.472 ms. All twelve integration cases
and ten independent signer cases passed. It performed twenty synthetic collection
requests, one synthetic send with a lost response, and read-only recovery without
another send or releasing reservations. Injected expiry still stopped before the
signer and sender. Exact admission-history reuse reported 1,130 SQL reads, one
validation and 1,129 reuses, with 22,533 bytes retained; no authorization verdict
was cached. Both phase profiles were valid.

This accepts that engineering check. It does not prove live RPC latency fits the
ten-second deadline or complete the held real devnet position.

## This implementation

The existing unsigned replacement allowance remains one. A **separate explicit,
one-time continuation allowance** now has an internal preparation contract.
Together they permit at most three immutable preparation generations: original,
replacement and continuation. This is new permission that must be explicitly
opted into by a future controlled coordinator; it is not an automatic retry.
There is no operational continuation CLI in this release.

The internal coordinator requires the exact original and replacement hashes and
`allow_unsigned_continuation=True`. It refuses before RPC when either identity
is wrong, the predecessor is not expired, STOP is present, the schema is unknown,
any exit signing/submission/accounting evidence or backend marker exists, or a
continuation already exists. It collects at most twenty fixed devnet requests
with unsigned simulation, holding a read-only snapshot during collection.

Persistence appends a single `admission_exit_continuation` row. The envelope links
both predecessor hashes to the new raw evidence, provenance and binding. The
original preparation, replacement, entry accounting, admission history and source
files remain unchanged. All three generations are replayed; missing or corrupted
continuation evidence never falls back to an older generation. Invalid evidence
also prevents lifecycle projection and signing-request construction.

The new record must preserve the entry receipt, acquired quantity, attempt
accounting and cumulative fee commitments. Its fee cap cannot increase and its
protected inventory cannot decrease relative to either predecessor. Its blockhash
must differ from both predecessors, and its quote slot cannot regress. The minimum
output comes from the freshly validated quote under the existing slippage policy;
it is not copied from an expired price observation. The new observation has its
own original ten-second deadline; no historical deadline is changed or widened.

The append is transactional. Final expiry, STOP, marker and 64 MiB ledger-size
checks run before commit; failures roll back the whole append. A committed record
that subsequently expires remains history and consumes the continuation slot.
It cannot authorize another continuation or reset the replacement slot. The
independent Node signer contract reads and validates all three linked generations;
its key access and one-send behavior are not invoked by this new CLI.

## Verification and scope

- 25 portable cases cover collection, immutable history, ownership, lifecycle,
  corrupt/orphan/extra records, no-fallback replay, repeated attempts, STOP,
  identity, schema, marker and signing exclusions, rollback, storage caps,
  provenance expiry and exact opt-in requirements.
- 14 independent Node contract cases validate three generations and reject
  changed lineage, missing history, reused blockhashes, changed holds/protection,
  changed attempt accounting and expiry. Mutations rebind the unsigned request
  and boundary hashes so the tests exercise semantic checks.
- Additional tests cover output privacy/exclusivity, rejected operational flags,
  mutually exclusive collection modes, changed source after collection,
  snapshot-cleanup failure and direct relationship constraints.
- Existing one-replacement checks and the connected replacement/signer/recovery
  profile are run as regressions. The new continuation is not yet connected to
  an actual isolated signer invocation, transport or receipt settlement.

Fixture setup uses disposable test keys and synthetic provider replies. No user
wallet or real RPC is used. The continuation itself is neither signed nor sent;
fixture setup may sign earlier disposable test transactions.
Synthetic clocks in the independent contract fixture exercise record ordering;
they are not a full-path latency measurement or a modification of signer clocks.

## Kali check

After fetching the pinned development commit supplied in chat:

```bash
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/unsigned_exit_continuation_cli.py" \
  --output "$PWD/radar-continuation-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, 25 portable cases and 14 independent contract
cases. Upload only the public report. No Docker rebuild or service restart.
Do not rerun the old live replacement command; its allowance is still consumed.

## Host acceptance and next integration gate

The 18:45:58 UTC Kali continuation report passed all 25 portable and 14 independent
contract cases. Archive SHA-256:
`d13f852a9084f9ecda1cdcaf83c56733a330b02500cd51bafa620e2047dbebbb`.
[Connected signer/transport rehearsal](CONTINUATION-EXIT-INTEGRATION.md) is the
next offline gate; the actual held position remains unresolved.


Connect this exact third generation to the existing isolated signer, one-send
transport, original-deadline checks and read-only recovery in a disposable
end-to-end rehearsal. Include interruption after commit, signing uncertainty,
lost send response, STOP and expiry; measure the full path on Kali. Only after
that acceptance should a narrowly scoped operational continuation command be
considered. Then reconcile the actual finalized receipt and close only its scoped
inventory/fee reservations.

Scanner, quote observer, sampling, alerts and frozen study rules are unchanged.
Availability captures on November 5 and 6 remain separate. No mainnet or real-money
pilot activation is included.
