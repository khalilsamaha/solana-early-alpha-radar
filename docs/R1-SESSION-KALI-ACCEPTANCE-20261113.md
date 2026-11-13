# R1 corrected session batch — Kali evidence accepted, 13 November 2026

## Disposition

Accept the bounded offline session/portable-evidence gate at producer revision
`aa3244c47221fa751f44d39c9b407d484390549e`, tree
`8fcaa515b79d971ca4ec8072be614f295e4239d4`. The earlier diagnostic-bearing batch
remains rejected as a clean result and is retained unchanged. This replacement
closes its Python 3.14/native Unix verification gap. Full R1 acceptance and live
launch remain blocked.

This was an independent review of supplied artifacts, not direct access to Kali
or a fresh RPC/provider/B2 observation. Recorded scenario journal times span
**13 November 2026, 07:45:07.075491–07:45:17.534993 CET** (06:45 UTC).
Those timestamps are host-reported, not independently attested. No current
balances, fees or provider execution are inferred.

## Input identities

| Supplied file | Bytes | SHA-256 |
| --- | ---: | --- |
| acceptance(1).zip | 541457 | `0975d85037c666acfa104323bd9b5f33ec9e511e85ac279f0ba8f152c1d35b47` |
| report(20261113-064545).json | 35431 | `bc2775cada8d89effe2ca2dec782a28b9c218ffd6d61c443f2b476c06250d8b3` |
| validation(9).log | 23777 | `d0a9145ac7295e822f4f1395cbf7c6a66bd7ee8ea2548cd0af198c6bf890f78c` |

The separate report and log are byte-identical to the bundled members. The outer
ZIP has exactly the expected ten bounded, uncompressed, regular mode-0600 members;
no duplicate, extra or encrypted member was accepted.

## Independent checks

- All **157 source fingerprints** match the corrected implementation, whose tree
  matches the published producer revision. Exact expected test-module list matches.
- Report and log agree on **160 tests**, zero failures/errors/skips, Python 3.14.6
  and websockets 17.4. The log has 160 successful named test outcomes, no traceback,
  and no match for the strengthened resource/runtime/async diagnostic rejection.
  Reported complete batch time is 36.771631 seconds; tests alone took 25.135 seconds.
- All eight archive lengths and SHA-256 identities match. Each manifest, exact
  stopped receipt, capture/journal replay and isolated restore independently passes
  under the pinned corrected source. This review did not rerun the fixture batch.
- Four clean cases (normal, different-size, idle, watch-expiry) retain
  `capture-stopped`. Cleanup, send, provider and operator-stop failure cases retain
  `transport-cleanup-failed`; complete evidence never promotes them to success.
- All eight scenarios report verified native Unix peer identity and one synthetic
  upstream attempt. Normal, different-size, cleanup-failure and watch-expiry also
  report actual Node consumers: one creation/token, one deliberate EOF gap, and
  zero upstream connections opened by the consumer.
- Live launch, complete gate, production modification, provider connection, real
  credentials, remote upload, retention, provider-origin attestation and
  precollection approval remain false in the relevant report/assessment fields.

Accepted status: `candidate-session-offline-passed-live-blocked`.
Do not repeat this passing batch without a material source change or new failure.

## Next engineering boundary reviewed

The accepted offline primitives already exist. The next work is their reusable
admission and supervision integration, followed by the separately authorized live
boundary; another unchanged fixture or B2 round trip does not close it.

| Existing component | What remains to bind or prove |
| --- | --- |
| `r1-session/session.py` and `archive.py` | Candidate accepts a caller-supplied Wire factory and closes the whole session. Bind approved admission, stable registry, supervised process and lifecycle ownership before a live factory can run. |
| `r1-runtime/boundary.py` and `credential.py` | Sealed-descriptor and process guards exist, but the launcher is fixed to offline fixtures and at most 12 seconds. A 24–48-hour policy is not approved by changing that constant. |
| `r1-service/lifecycle.py` and `integrated_backend.py` | Durable no-rearm ordering and disposable integration exist; receipts are explicitly synthetic. Actual direct-owner shutdown, unique shared ownership and production rollback require separately observed identities and real receipts. |
| `r1-registration/proposal.json` and `contract.py` | Draft measurement terms exist; approval/exposure fields remain unapproved or null. Local quality cannot establish historical coverage, provider acknowledgement, billed events or source adequacy. |
| Candidate archive plus prior fixed B2 round trip | Local preservation and one fixed remote round trip exist. Actual live-session retention duration, capacity allocation and remote lifecycle remain unverified. |

A future bounded read-only host inventory is needed before fixing the production
handoff: exact scanner/container and image identity, restart policy, UID/namespace,
current connection owner and endpoint, stable registry identity, and available
storage/resource allocation. Use explicit allowlisted metadata only; no environment,
credential content, arbitrary command lines, service mutation or provider calls.
No such fresh host inventory was performed in this artifact review. Its results
would inform the rollout binding, not authorize a rollout or prove provider closure.

The next source increment should join these existing pieces with admission closed
by default, preserving the stable consumed claim and refusing automatic resume or
rollback after uncertainty. Before a real provider pilot, the production handoff,
credential provisioning, supervision profile, live preservation/capacity and fixed
measurement/exposure terms must all be concretely reviewed and authorized. This
acceptance does not activate a provider, merge main or extend the effort budget.

## Agenda and E0

R1 is still completing collector/preservation prerequisites. November 12–18 is the
original five-working-day allocation; remaining effort is unknown without an
actual ledger. November 19 remains at risk. No confirmation window has started;
any pass still needs 21 complete UTC days after prerequisites and sealed approval.
Day 14 permits futility only. December 31 remains the decision checkpoint.

E0 is independent and blocked with holds preserved. Its last accepted operational
observation remains November 9, 18:50:41 CET. No E0 closure receipt, journal update
or historical-coverage evidence is supplied by these synthetic R1 artifacts.
November 20 may be complete only if required closure evidence exists; otherwise
retain blocked-with-holds-preserved. Reopen only for exact closure-relevant
finalized receipts, material journal discrepancies, or credible coverage evidence
meeting the E0 closure contract. RPC absence, expired blockhashes and matching
balances cannot establish non-execution.
