# Exit timing evidence — November 4, 2026

The controlled replacement command passed its seven host boundary checks, but its
real devnet attempt expired before signing. It collected twenty RPC responses,
preserved the original preparation, appended its one replacement and then stopped
with `fresh-signing-expired`. No private key was accessed and no signature or send
was attempted. The subsequent read-only audit confirmed the same replacement,
no signer markers and the original inventory and fee holds.

The saved record timestamp is 06:16:00.968 UTC and its deadline is 06:16:02.416 UTC:
1,448 ms apart. The record timestamp is assigned before evidence review, write and
commit. It is not a commit completion timestamp. The failure report was produced
120.394 ms after the deadline, which does not establish the exact expiry crossing
or mean a 121 ms deadline extension would solve execution. Signing and transport
had not started. Another replacement is not authorized by this diagnostic release.

## Two separate measurements

`position-book/exit_profile_cli.py --action inspect` reads and validates the saved
active preparation under the existing source/read locks and read-only journal
connections. It exports twenty request/reception intervals, inter-request gaps,
last response to collector delivery, delivery to record timestamp and remaining
validity at those recorded points. It reports commit completion and post-commit
headroom as unknown. It does not collect new observations, open the private key,
replace evidence, sign, send or release funds. Request intervals include client
work and must not be described as pure network or provider latency.

The default `check` action exercises the existing full replacement integration in
disposable fixtures, with synthetic RPC replies and an actual isolated test-key
signer. It observes collection, source replay, evidence/provenance review,
eligibility checks, writable transaction entry/commit, replacement write, signing
handoff, signer backend and transport. It retains partial timing if the original
freshness guards refuse the attempt. A separate synthetic delay after persistence
reproduces the host's unsigned-expiry state and verifies zero signer/send calls,
preservation and refusal of another collection. No timing threshold is widened.

The profiler is installed only inside the standalone offline harness. Importing
it installs no patches. Instrumentation is restored after exceptions and rejects
nested installation. Diagnostic clocks never become execution clocks. Timings are
bounded to 1,024 allowlisted spans with no arguments, keys, signed bytes, raw errors
or arbitrary stage labels. Repeated writable journal reads also create transaction spans; CLI output aggregates
these by stage while the report retains bounded detail. Writable transaction
commit/rollback semantics remain
those of the original context manager. Read-only transaction overhead remains
inside its parent phase.

Inclusive spans overlap. Exclusive durations subtract directly recorded children;
unmeasured gaps, instrumentation overhead and provider latency remain limitations.
Fixture setup and the deliberate wait for the original synthetic preparation to
expire are outside the first measured replacement attempt. The command can take a
few minutes to create fixtures and complete the full checks; the timed attempt is
only part of that total.

## Validation and host procedure

Ten targeted tests cover clocks, nesting, caps, exception cleanup, original
transaction semantics, read-only evidence preservation, corrupt history rejection,
expired-but-persisted evidence, command/output guards and the connected CLI. The
connected exercise retains twelve integration checks and ten independent signer
contract cases. The new test module is explicitly assigned to CI partition 3.

From the pinned development commit, run `--action inspect` with the existing
wallet/pool/private directory and a new public output file. Then run the default
check with only `--output`. The offline action rejects operational scope; neither
action accepts signing, submission, retry or deadline flags. Outputs are exclusive
mode-0600 gzip JSON files. No service installation, Docker rebuild or study change
is needed. Preserve all existing journals and do not rerun the execution command.

## Next gate

Compare the saved live request intervals with the host's offline phase profile.
Target measured overhead while retaining independent source/ownership validation,
STOP checks and original freshness bounds. A performance change still requires
regression coverage and host validation. The consumed replacement and held
position need a separately reviewed lifecycle solution; a profile pass does not
reset either. Finalized exit accounting and scoped closure remain incomplete.
