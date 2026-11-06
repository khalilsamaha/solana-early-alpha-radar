# Exit collection connection reuse and remaining gates

## Evidence driving this change

The November 6 saved timing report records 5804 ms from collection start to
handoff. Twenty sequential RPC request intervals sum to 5042 ms. The signed
acknowledgment row was recorded 262 ms before the original ten-second deadline;
post-signing work subsequently exhausted the window before any application send
boundary. Row timestamps precede commit completion. This does not measure pure
signing time or establish that the signed wire was never broadcast elsewhere.

The existing urllib handler explicitly sends `Connection: close` for each
request. Reusing its opener therefore does not reuse its TLS connection.

## Implementation

Only the default transport used by `admission_exit_capture.collect` changes.
`exit_rpc_session.Session` maintains a verified HTTPS connection for that one
collection. Injected offline openers retain their existing behavior. A complete
server-directed close permits the *next* logical request to establish another
connection. A failed, truncated, oversized, unread or partially consumed exchange
closes and disables the session; it is never retried. Every collection closes its
session on success or failure.

The fixed devnet URL, POST-only read/simulation allowlist, twenty-request cap,
original request sequence, simulation arming, response validation, original
freshness deadline, STOP checks and final evidence hashes remain in force.
The session forwards no caller credentials or custom headers, uses default
certificate and hostname verification, and does not consult proxy environment
variables or follow redirects. Response reads remain capped at 4 MiB plus the
oversize detection byte, with remaining request time checked around each chunk.
The existing collectors still validate JSON-RPC IDs, shapes and economic inputs.

The public collection report adds `rpcSession`: request count, connection-object
count, completed response count, closed flag and zero retries. Injected openers
report null. These are transport diagnostics, not economic or execution approval.
`connectionsOpened` counts connection objects created, including failed attempts;
it does not claim successful TLS handshakes. Server-requested closure can prevent
reuse, and a dropped idle connection fails the collection without automatic retry.

No scanner, quote observer, frozen study, sender, signer, ledger migration,
reservation policy, GitHub Actions configuration or backup setting changes.
No live collection or transaction was performed during this development.

## Validation and host check

Nine new tests use local Unix socket pairs and real HTTP framing with synthetic
provider bodies. They cover reuse across twenty exchanges, server closure,
redirect/status errors, dropped/truncated/chunked responses, size/read/deadline
limits, fixed endpoint/header restrictions, and the connected collector's exact
proof sequence, expiry and STOP behavior. TLS defaults are checked; socketpair
tests do not measure real TLS latency or certificate exchange.

Also run the five existing admission exit collector tests (including their
nineteen-case offline exercise), ten existing exit profile tests including
connected signing/expiry, source hygiene and partition coverage. No hosted CI
pass or live deadline acceptance is implied by local tests.

After checking out this release in the separate development checkout, the Kali
check is:

```bash
python3 -E -s -m unittest discover \
  -s "$HOME/apps/solana-radar-dev/position-book" \
  -p test_exit_rpc_session.py -v
```

This uses disposable test state and local socketpairs only. It does not open the
user's rehearsal journals, access their private key, call public RPC, install a
service, or rebuild Docker. It is not an execute command.

## Remaining engineering order

1. Accept the transport checks on Kali; establish real collection latency only
   in a separately scoped observation path that cannot replace the held attempt.
2. Design read-only chain reconciliation for the expired signed, locally
   unsubmitted exit, checking its recorded signature and blockhash validity.
   Neither local freshness expiry nor a single absent signature result can
   release funds or authorize re-signing. Preserve all three preparation
   generations, signature evidence and reservations until this gate is resolved.
3. Rehearse the complete collection/signing/send/recovery deadline path, then
   consider a separately authorized controlled devnet operation. Synthetic speed
   alone is insufficient, and this release grants no new operation authority.
4. Consolidate the tested increments under the agreed batched workflow. PR #78
   remains separate; account-blocked CI must not be represented as a pass.

## Closed availability study

The completed fixed window is October 30 00:00 UTC to November 6 00:00 UTC.
Its final report has 304 unique predictions, 302 known labels and seven UTC dates.
The excluded group has 15 known labels against the registered minimum of 20, so
its state remains `insufficient-fixed-window-evidence`. The model excluded 14 of
45 provider quote failures while retaining 256 of 257 successful quotes. These
are descriptive availability results, not a passed study or a profitable strategy.

Among selected returned quotes, mean quoted change was -7.18% at 30 seconds and
-13.89% at 120 seconds. Failed exits are not included in those means. Do not
extend this fixed study, relax its guard, refit into its evaluation window or
activate the model. Any further availability confirmation needs a separately
registered prospective study. Execution reliability and positive net economics
remain separate requirements before a real-money pilot.
