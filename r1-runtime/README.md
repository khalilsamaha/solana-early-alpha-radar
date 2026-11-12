# R1 credential delivery and supervised shared worker — offline only

The Docker boundary is accepted on Kali at `747f44ed`: 314 core checks, 20
container-control checks and 226 scanner checks; all 123 source hashes match.
All three owned disposable containers were removed. Report SHA-256:
`8107fe3cc7495a184ab49ad314d2c6245f7389c3e7a16607a74f9c248263d4c5`.
The uploaded normal session (25,861 bytes) independently replays exactly, SHA-256
`6a0e45f8650e752eac808d1c50d2eff4751f834d6c27bfbd0fa0362d9eeca0ac`.
Kali reports replay for failed cleanup too; its separate ZIP was not uploaded,
so independent replay is claimed only for the normal session. Production startup
and rollback remain untested.

This increment addresses private-file loading, descriptor delivery and supervision
of the shared owner/capture/wire path inside one bounded worker. It is not a live
launcher, and it does not enable any provider connection or paid subscription.
The public runner accepts an output directory only, generates synthetic credentials
in a temporary private directory, then deletes those input fixtures.

`credential.py` is a library for future reviewed live integration. It walks open
directory descriptors with no-follow semantics, rejects writable untrusted
ancestors, requires a same-owner mode-0700 parent and a single-link mode-0400/0600
regular file of 16–4096 printable ASCII bytes. It rejects whitespace/newlines,
symlinks, FIFOs, oversized content and detectable identity/content changes.
It never prints values, paths or exception details. This format is one value,
not an environment file. Do not prepare or upload a real key for this rehearsal.

The handoff uses a Linux anonymous memfd, mode 0600 and sealed against write,
growth, shrink and seal changes. The memfd's name is a constant. Only its descriptor
number enters worker argv; no credential value or path is passed to the worker.
The parent closes its copy immediately after spawning. The worker checks the
anonymous file and all seals, reads at most 4097 bytes, and closes its copy before
using the synthetic value. This is not a claim of Python memory zeroization,
protection from root/same-user process inspection, or absence of swap copies.

The supervisor launches a fixed offline worker exactly once per owner directory.
It persists the attempt before reading credentials or spawning, retains the claim
on success/failure, and never automatically restarts or renews it. The lock covers
cooperating runs in that directory only; it does not establish host/IP-wide
provider exclusivity. Deleting the directory or choosing another one is not
prevented by this primitive. A live launch still needs a bound registration and
an operator-controlled global connection handoff.

The worker reuses the accepted Linux bootstrap: parent-death SIGKILL with PID
recheck, zero core size, 256 MiB address space, five CPU seconds, 44 MiB file size,
32 descriptors and a ten-second alarm. Internet/DNS and child processes are denied.
The parent independently bounds wall time at 12 seconds, then TERM (0.25 seconds),
KILL and reap (one second); inherited environment is the existing minimal allowlist.
These are short offline limits, not an approved 48-hour live service policy.

The normal and cleanup-failure cases use the real credential-redacting Wire and
shared Owner with an in-memory protocol peer, a separate capture thread, journal,
export and restore. Discovery is drained in-process; this test does not repeat
or replace the accepted Docker/Unix IPC evidence. Normal research retirement
preserves discovery. An uncertain cleanup aborts upstream. A deliberate tainted
worker error verifies discarded stdout/stderr; a stalled worker verifies forced
kill/reaping. Tests also exercise parent death and attempt reuse refusal.

Reports contain no credential value, encoded variant or credential fingerprint.
The runner scans retained output for its generated sentinels. A successful result
is `offline-runtime-boundary-passed-live-blocked`. Upload `report.json` and
`session.zip`; on failure preserve the directory and upload the available report.
A clean process exit alone is insufficient: source pins, manifest binding,
worker receipt and independently restored package must also match.

## Remaining work before activation

Integrate these primitives into the reviewed live service with a bounded admission
registration, persistent no-rearm policy, stop/recovery behavior, private credential
provisioning, and actual production handoff/rollback. Freeze measurement selection,
missingness, coverage and cost terms before any pilot. Numeric funding/exposure
approval and real-session preservation/retention remain open. The original 0.05 SOL
and 0.02 SOL figures are proposals, not approved limits. No ML fitting or trading
is authorized by this work. The existing five-working-day R1 engineering effort
cap is unchanged; this increment does not reset it.

Full-gate Kali validation precedes PR/CI consolidation and a merge decision.
References: [Linux memfd](https://man7.org/linux/man-pages/man2/memfd_create.2.html),
[file seals](https://man7.org/linux/man-pages/man2/F_GET_SEALS.2const.html).
