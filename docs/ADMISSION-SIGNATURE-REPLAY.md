# Exact signature replay — November 2, 2026

## Evidence and decision

The November 2 host reports passed the strengthened 24-case lifecycle exercise
and 19-case admission-timing exercise. The live no-write observation completed
20 devnet requests with 74 ms before its original expiry. Collection took
9.253 s, the two extra locked source reads took 1.811 s and 0.689 s, and raw
admission validation took 0.190 s. Total wall time was 11.945 s; quote age was
9.927 s because quoting began after initial local work. This establishes one
successful observation, not adequate signing/submission headroom.

A local profile of one full synthetic source read took 0.784 s. Fifteen Node
verification subprocesses accounted for 0.581 s. These are local fixture results,
not projected Kali timings or RPC timings. Repeated historical signature checks
are a concrete optimization target; the ten-second quote limit stays unchanged.

## Change and boundaries

Only the admission-timing observer opts into `exact-signature-replay-1`. A bounded
in-memory set remembers up to 64 successfully verified exact canonical wire byte
strings for that observation. Every call still decodes the current bytes. New or
changed bytes go through the original Node Ed25519 verifier, with all signers and
the original timeout/environment rules. Failures are never remembered. At capacity,
verification proceeds normally without adding another entry. Scope exit, including
exception exit, clears the set. Nested scopes have their own set and restore the
outer scope. There is no persistent cache and ordinary verifier callers remain
uncached.

Files, journal hashes, ledger identity, receipt reconciliation, STOP checks, account
funding, simulation evidence and deadlines are not memoized. All five source reads
in this observation remain. A signature proves bytes were signed, not that their
transaction is current, funded, finalized or safe to execute. All those independent
checks remain mandatory. The source lock still cannot control external wallet use.

The public timing report adds aggregate verification call/process/reuse counts and
verifier duration. No wire bytes or private keys are exported. The scanner, quote
observer, study registration, sampling, notifications and backup jobs are unchanged.
No signing, submission, admission ledger or reservation is introduced.

## Validation

63 targeted local tests passed: 39 journal/read-only tests, 10 existing collector
tests, eight timing tests and six signature-replay/source-integration tests.
The complete-source comparison retained all five source reads, the same public
assessment and unchanged source bytes. Verifier processes fell from 44 to seven
(37 exact-byte reuses). With fake RPC responses, local elapsed time fell from
2.207 s to 0.764 s. This is a synthetic local measurement, not a host speed claim.
Changed receipts and STOP arriving after verification reuse still blocked the
observation. The 30-case portable exercise includes 11 new reuse-specific cases.

## Host acceptance

Fetch the pinned development commit provided in chat. Run:

```bash
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/admission_timing_cli.py" \
  --output "$PWD/radar-admission-replay-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: 30 offline cases passed. These use public signed fixtures and Node's
verifier, without private keys, source-journal writes or network calls.
Then perform one observation:

```bash
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/admission_timing_cli.py" \
  --observe-devnet \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --maximum-exit-attempts 2 \
  --maximum-exit-fee-lamports 10000 \
  --maximum-total-fee-lamports 30000 \
  --output "$PWD/radar-admission-replay-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Upload both public reports, including `unavailable` if it occurs. That result
publishes a diagnostic and exits 2. Do not retry solely to obtain a pass or delete
an occupied admission directory. No rebuild, service restart or live send is needed.
Compare verification counts, source-read time and original-deadline headroom; RPC
variability means one before/after sample does not establish a latency distribution.
No new numerical headroom threshold is invented as a substitute for measuring the
still-missing durable commit/sign/send stages.

## November 2 host acceptance

The 30-case host check matched a fresh source replay. The live check used seven
verifier processes for 44 calls and retained 1,131 ms before the original expiry.
The two extra source reads totalled 0.707 s, versus 2.500 s previously. Total wall
time was 10.002 s. No source changes, signatures, sends or reservations occurred.
The next [isolated durable rehearsal](DURABLE-ADMISSION-REHEARSAL.md) measures
storage and raw revalidation without consuming the operational slot.

## Next gate

If host evidence shows useful headroom, design the bounded durable-admission
rehearsal with separate expiry checks at commit and signer handoff. Otherwise
profile remaining costs before adding writes. Delayed exit, ambiguous-send recovery,
closed accounting and execution economics remain independent gates. The November
3, 5 and 6 availability-study preservation dates remain unchanged.
