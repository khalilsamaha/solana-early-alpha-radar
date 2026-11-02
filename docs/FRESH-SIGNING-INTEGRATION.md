# Fresh collection-to-signing integration — November 2, 2026

## Accepted foundation

The isolated durable-admission host run passed all 22 cases. Its live unsigned
collection and commit completed in 9.771 seconds with 1,754 ms remaining. The
reservation stage took 664.565 ms. Read-only recovery returned exactly the same
reservation, evidence/policy/message/source hashes and original deadline, without
RPC requests. This accepts the rehearsal gate, not sustained latency reliability.
The isolated journal remains historical and is never promoted to operational use.

PR #70 merged the accepted foundation to main commit
`777a355897270addccf3bd6218e2352594d0c860` after all ten CI groups passed. A prior
run reached the 10-minute limit; isolating the heavy closure suite fixed the job
layout while preserving all tests. Two coverage tests verify unique module
assignment. This new increment follows the consolidated source and uses the agreed
local-tests-first rhythm; it is not merged or deployed by that consolidation.

## What this increment implements

`position-book/fresh_signing.py` connects the actual bounded fresh collector to
the existing durable handoff and independent devnet signer. This is an internal
API with explicit private-key opt-in. The supplied CLI exposes only synthetic
checks; there is no live action, service installation or transaction sender.

One attempt:

1. Checks explicit opt-in, fee limits, STOP and a vacant fixed operational slot.
2. Collects its own raw devnet evidence, including one unsigned simulation, within
   the existing 20-request limit. Reports/files are not accepted as raw inputs.
3. Keeps the minimum original deadline. If the durable request would have a later
   deadline than another required observation, the attempt is refused.
4. Reacquires the source lock and rechecks vacancy to exclude a competing attempt.
5. Uses the existing raw reviewer and two locked source reads to commit the
   reservation, exact signer request and uncertainty boundary in that order.
6. Checks deadline, monotonic budget and STOP immediately before a single backend
   invocation. The independent backend revalidates the committed request and
   records its own one-shot attempt before touching its dedicated key.
7. Validates the returned signature and saves the accounting handoff. No RPC
   submission follows. A late acknowledgment stays recorded without a freshness
   claim; failed or ambiguous acknowledgments require recovery.

The small `signer_handoff` refactor extracts its existing locked body for use by
this integration. It preserves the standalone dispatch interface and its existing
failure/recovery behavior. The source lock remains held through backend dispatch
and acknowledgment persistence.

## Failure and recovery behavior

An existing or partial operational slot blocks fresh collection. A boundary
failure, timeout or lost backend response does not authorize another attempt.
The report uses unknown signature/key-access values when invocation occurred but
its outcome cannot be established. `recover` reads an existing private signer
acknowledgment and idempotently records it; it has no collection/signing argument
and creates no new signature. The reservation remains held.

A post-signing expired deadline or STOP does not discard a signature. It also does
not authorize submission. The separate sender must still apply its own original
freshness, blockhash, fee, STOP and one-send checks. The private journals and
acknowledgments must be preserved; no reset or release was added.

The controlled source lock cannot prevent unrelated external wallet activity.
This is not wallet-wide allocation, an arbitrary route signer, a mainnet path or
an economic readiness signal. Separate delayed entry/exit operation is still an
integration acceptance gate.

## Tests and host acceptance

36 targeted local tests passed: nine new integration tests, 20 existing durable
handoff regressions and seven independent backend regressions. The new portable
exercise has 17 synthetic cases. It uses an existing public signed fixture and
creates no signatures or private keys.

Two full-source local integration tests used disposable keys and the real
independent signer with fake RPC responses through the actual collector/parser:

- fresh collection -> committed boundary -> independently signed acknowledgment
  -> accounting outbox, with original source files unchanged;
- real acknowledgment saved but parent response lost -> key removed -> recovery
  from the saved acknowledgment, without another signer or collection call.

No network request or transaction was broadcast in these tests. Fake-RPC elapsed
time is not a host or provider latency benchmark.

Run the pinned `fresh_signing_cli.py --output ...` command supplied in chat. Expect
17 cases and `offline-checks-passed`. Upload only its public compressed report.
No wallet path, rebuild, service restart or existing rehearsal modification is
required. Live signing is deliberately not exposed by this acceptance command.

## Remaining sequence

After the synthetic host gate, integrate the bounded operational entry sender with
this fresh path and measure the complete deadline budget before a narrowly scoped
devnet run. Preserve uncertain signatures/submissions for recovery rather than
recollecting or refreshing evidence. Then verify the separate delayed exit and
final accounting in the same lifecycle. Mainnet-specific validation, pilot limits
and economic acceptance remain separate gates. The November 3, 5 and 6 study
captures and the November 6 00:05 UTC review remain unchanged.
