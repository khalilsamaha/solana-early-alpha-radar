# Entry deadline profiling — November 3, 2026

The read-only devnet report captured at 04:51:54 UTC passed raw admission
validation. Twenty bounded requests and local checks took 8.649 seconds, with
2.454 seconds remaining before the original evidence deadline. That remainder
excludes durable admission, private signing and submission. It is a single live
observation, not a guarantee that the complete execution path will finish on time.

PR #72 consolidated the previous three increments on main
`61017ff1017f8c0d62a82708555fa91af15fcbd2`. All twelve CI groups passed. This is the
first locally tested development increment of the next batch; no new PR or full
CI run is needed until the agreed consolidation checkpoint.

## What changes

Opt-in bounded timing hooks now expose nineteen phases in the existing entry
path: collection, admission initialization, both source rereads, reservation,
signing handoff and boundary, independent signer invocation, signed acknowledgment,
accounting handoff, sender initialization and validation, sender source replay,
preflight, durable send boundary, transport call, acknowledgment and projection.

Hooks are disabled unless an internal `entry_profile.capture` scope is active.
Disabled hooks do not read clocks or create report rows. The original operational
clocks, checks, request order, locking, deadlines and single-send behavior are
unchanged. No validation read is removed or replaced by a cached result in this
increment. No new durable profile table, background service or provider call is
introduced.

The bounded report contains fixed stage names, optional parent stage, start/end
timestamps, monotonic durations, original-deadline headroom and the actual existing
send-guard timestamp. It contains no wallet keys, signatures, serialized messages,
raw provider replies or exception text. At most 32 spans are retained. Invalid
diagnostic clocks and overflow invalidate the profile; they do not hide committed
execution records or rewrite an unknown send into success/failure.

## Host exercise

`position-book/entry_profile_cli.py` accepts only `--output`. It uses owned temporary
source journals, disposable test keys, the actual isolated signer and synthetic
provider replies. Python socket access is blocked. Fixture construction is outside
the timing scope. A synthetic lost send response is followed by keyless, stopped
receipt recovery and repeated recovery without another send. Temporary keys and
journals are removed even if setup fails partway through.

The successful state is `offline-entry-profile-passed`, with seven connected checks
and nineteen completed spans after the attempt-verification increment (the original
profile had six checks). The additional check validates scoped verification counts
and cleanup. A failed exercise publishes partial sanitized
evidence with `review-required` and exits 2; preserve that report. Existing output
is not overwritten, and output permissions are 0600. There are no operational
directory, wallet, pool, signing, submission or live observation flags.

Run the pinned checkout command supplied in chat, then:

```bash
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/entry_profile_cli.py" \
  --output "$PWD/radar-entry-phase-profile-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

No Docker rebuild, service restart, airdrop or access to the existing private
rehearsal directory is required. Upload the public report. The original six-check host exercise passed
on November 3 at 05:04:56 UTC. The updated seven-check verification-reuse
exercise passed at 05:56:41 UTC, with all nineteen spans complete. See the
[accepted comparison](ENTRY-ATTEMPT-VERIFICATION.md).

## Local validation

Twelve profiling tests pass, including the complete disposable-key CLI, diagnostic
clock failure/overflow, nested timings, bounded output, original-deadline refusal,
lost-response recovery, incomplete reports and partial setup cleanup. All 81
existing tests across fresh entry, fresh signing, signer handoff, admission
submission and locked admission pass. Both CI partition coverage/stability checks
and tracked-source hygiene pass. An AST comparison of the five instrumented
modules confirms their original operations and ordering after diagnostic hooks
are removed. These checks do not substitute for Kali timing or live execution.

## Interpretation and next decision

Timings are inclusive. In particular, `sender-validation` includes
`sender-source-replay`; do not add them together. Gaps between spans are not
attributed. A completed `send-request` means normal control flow, not delivery or
finality: the successful exercise intentionally returns `submission-unknown`.
Lazy synthetic reply construction can add local test overhead. Real network and
confirmation latency are absent. Do not add this sample mechanically to the
separate live observation or treat its larger synthetic headroom as an improvement.

The accepted Kali sample measured 1,196.250 ms across three source replay spans,
about 79% of 1,519 ms post-collection time. Sender source replay alone was
876.113 ms. The 8,242 ms synthetic send-guard headroom does not replace the
2,454 ms live unsigned observation. The next
[attempt-scoped verification increment](ENTRY-ATTEMPT-VERIFICATION.md) shares only
successful exact-byte authentication across signing and submission. Journal reads,
source identity, raw validation, STOP, original expiry and recovery are retained. The live controlled
entry/exit acceptance gate still requires separate review. This profile is not
execution approval or evidence of profitability.

Availability-study captures on November 3, 5 and 6 and review on November 6 at
00:05 UTC / 01:05 Amsterdam remain unchanged. Scanner, quote observer, study,
Telegram, production deployment and backups are unaffected by this source release.
