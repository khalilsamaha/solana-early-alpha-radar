# Fresh exit transport integration — November 2, 2026

This increment connects a newly collected exit to its independent signer and the
bounded one-send devnet transport. It starts from already reconciled open-entry
accounting. It does not choose when a strategy should exit, install a service, or
expose an operational execution command.

## Boundaries

`position-book/fresh_exit.py` requires two exact internal opt-ins before source
access: private-key signing and devnet submission. Its production wrapper binds
the existing restricted Node signer. The adapter seam is for trusted tests.

The coordinator first requires a vacant exit preparation/signing slot and no
orphan backend marker. It uses the actual twenty-request exit collector and
atomic provenance-checked preparation. Only a preparation created by this call
may continue. Existing, expired or partially completed preparation is inspection
state; a repeated call cannot refresh, sign or send it.

The preparation retains its original ten-second collection expiry. The
coordinator's thirty-second monotonic budget begins before collection, and is
not restarted for signing or transport. Exact preparation identity and expiry
are checked at signer invocation and at every sender request, including the
send after its durable boundary. The sender independently replays source,
accounting, collected evidence, exact signed wire, fee cap and blockhash.

| Outcome | Behavior |
| --- | --- |
| Collection or preparation fails | No signer or sender; partial request counts remain visible |
| Signer response is lost | Signing attempt remains uncertain; no automatic send |
| Signature arrives after expiry | Historical acknowledgment retained; no send |
| STOP, clock regression or expired budget during preflight | Next request refused |
| Deadline expires after committed send boundary | Unknown attempt retained, even if no request reached transport |
| Send response is lost | Observe only the recorded signature; never resend |
| Send acknowledgment arrives late | Retain it without claiming timely completion |
| Finalized receipt is observed | Raw transport evidence only; accounting and closure still required |

At most twenty collection and five sender requests occur per call. Recovery
uses the existing bounded receipt path and never invokes collection or signing.
It works after expiry/STOP without the wallet key or signer acknowledgment file.
An unfinished signing stage instead uses the existing keyless backend recovery;
that action does not resume submission.

The exit quantity is the acquired delta, with unrelated inventory and held fees
protected by the existing accounting and preparation checks. No reservation is
released and no new cycle is authorized. External wallet activity remains outside
cooperating local locks. An RPC response is not proof of a fill or profitability.

## Validation and host gate

The portable host gate runs 21 cases using existing public signed fixtures,
actual bounded collectors, fake HTTP responses and temporary journals. It does
not read wallet keys, open sockets, create signatures or submit transactions.
All 35 targeted tests passed: twelve new integration tests, seven existing
collected-exit tests, four restricted-signer tests and twelve transport tests.
The new full-source test exercises the actual independent signer with a disposable
test key, exact one-send transport with a lost response, and keyless receipt
recovery. Source hygiene and two CI partition coverage/stability checks also pass.
The November 2 host report at 07:42:19 UTC passed all 21 portable cases and
exactly matched the expected contract. No live execution was performed.

Use the pinned `position-book/fresh_exit_cli.py --output ...` command supplied in
chat. The CLI accepts no wallet, directory, execution or signing switches.
Upload its compressed public report. No scanner/observer restart or deployment
is required.

Next: connect recovered exit evidence to final accounting, fresh residual
balances and scoped closure; then measure the connected path on the host before
any separately authorized controlled devnet execution. Mainnet validation,
pilot limits and economic qualification remain separate gates.

The November 3, 5 and 6 captures and November 6 00:05 UTC review are unchanged.
