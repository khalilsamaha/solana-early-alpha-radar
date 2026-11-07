# Read-only chain observation for the held signed exit

## Accepted host evidence

Kali passed all ten exit RPC session tests in 4.035 seconds on the pinned
`4e0617ac0638befdc0c2613c8a185c2da4246f1a` revision, including explicit HTTPError
cleanup with ResourceWarning enabled as errors. This accepts the offline
transport behavior on Python 3.14, not live timing or execution.

The held preparation is
`d8ab974e819a953ecf015aa3acee403e8ca30f822bac72e58d92263218f9dd97`.
It has a saved signature but no local application send boundary. Its original
freshness deadline expired. The unsigned continuation was consumed, and the
signature, all three preparation generations and reserved funds remain held.

## Why a separate diagnostic

Existing `exit_submission.recover` queries receipts only after a local send
boundary. That behavior remains intact. `signed_exit_chain_cli.py` handles the
narrow inspection case of an expired signed, locally unsubmitted exit. It has
no signing, sending, replacement, persistence-to-ledger, release or execute action.

It requires an explicit directory, wallet, pool and exact preparation SHA. Before
any RPC it replays the current preparation, signing journal, backend attempt and
acknowledgment, transport history and scoped lifecycle. Any identity mismatch,
corruption, nonexpired preparation, send boundary or inconsistent position refuses
observation. It retains cooperating source and shared admission read locks, then
revalidates local evidence after the RPC requests. STOP does not prevent this
read-only diagnostic. Queries never authorize action against STOP.

Four maximum fixed devnet requests, in order:

1. `getGenesisHash`, verifying the devnet genesis.
2. `isBlockhashValid` for the *saved* blockhash at finalized commitment, with the
   minimum context slot derived from the saved active generation.
3. `getSignatureStatuses` for the *saved* signature with
   `searchTransactionHistory: true`; returned context must be no older than the
   blockhash observation, and status fields are validated without type coercion.
4. `getGenesisHash`, again verifying devnet.

The endpoint cannot be overridden. Requests have a thirty-second aggregate start
budget, ten-second per-request socket timeout ceiling, no retries, no redirects
or environment proxies,
and 64 KiB response caps. Local validation plus collection has a 120-second
acceptance budget. Deadline failures discard the observation; this is not a
hard preemptive timeout for arbitrary local work or slow response streaming.
Original execution deadlines are never changed or reused as observation validity.

## Interpretation

| Observation | Meaning | Permitted action from this report |
| --- | --- | --- |
| Signature absent, blockhash valid | Provider did not find the signature; saved hash still valid at finalized commitment | Preserve holds; no retry |
| Signature absent, blockhash invalid | Provider did not find the signature and reports the hash invalid | Preserve holds; non-execution is not proven |
| Signature found, any confirmation | Provider reports a status for the exact signature | Inspect exact receipt before accounting |
| Invalid/local conflict/provider failure | No complete observation | Preserve journals and investigate |

Even a finalized status is not a validated receipt or reconciliation of token
movements/fees. The report never marks an attempt released or a position closed.
No status, including absence plus invalidity, allows a fourth preparation,
re-signing, resubmission, new entry or mainnet use. A later recovery policy must
account for provider history limits and independently validate any found receipt.

The public report includes hashed identities, sanitized status fields, context
slots and existing scoped accounting. It excludes the signature, signed wire,
wallet address, provider error text and all private keys. RPC reads necessarily
send the public saved signature and blockhash to the fixed devnet endpoint. The
only requested output write is a new private-mode public report outside source
and admission directories. Local journals remain read-only and byte-preserved.

## Validation and operator sequence

Eight new tests cover valid/invalid hash with absent signature, STOP, found
processed/confirmed/finalized success/failure, exact identity mismatch, corrupted
acknowledgment, lost-response send boundary, wrong cluster, stale/malformed slots,
timeout, changed backend evidence during RPC, response cap, blocked sender,
strict status types and CLI scope/output guards. Fixtures use public signed test
transactions, temporary journals and synthetic replies; no public RPC or user key.

Run the targeted offline tests on Kali first. Then run the CLI once with the
known preparation SHA and upload its public JSON.gz report. It makes at most
four public devnet reads; no Docker rebuild, wallet funding, private key access,
service restart or execution flag is needed. Do not rerun an execution command.

## Remaining gates

1. Review the bounded chain observation for the held attempt.
2. If found, collect and validate its exact receipt before token/fee accounting.
   If absent, define a separate conservative expiry/non-execution recovery policy;
   this diagnostic deliberately does not implement a replacement transition.
3. Once the held attempt is resolved, measure live collection timing and rehearse
   the connected deadline/recovery path before any new controlled devnet action.
4. Consolidate locally tested changes under the batched workflow. No merge,
   PR #78 update, GitHub Actions, billing, scanner, observer or backup changes
   are included here. Availability study conclusions remain fixed and do not
   establish profitability or authorize a real-money pilot.

## RPC references checked for this implementation

- https://solana.com/docs/rpc/http/getsignaturestatuses
- https://solana.com/docs/rpc/http/isblockhashvalid

The first documents historical signature search; the second describes validity
at the requested commitment and minContextSlot. The conservative refusal to infer
non-execution or release funds is this project's policy, not a claimed guarantee
from either RPC method.
