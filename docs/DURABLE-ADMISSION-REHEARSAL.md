# Isolated durable admission rehearsal — November 2, 2026

## Accepted input and goal

The exact-signature replay host exercise passed all 30 cases. Its live unsigned
observation completed with 1,131 ms remaining, compared with 74 ms before the
optimization. The two additional source reads fell from 2.500 s to 0.707 s;
44 signature checks used seven verifier processes. These two samples demonstrate
an improvement, not a reliable execution-latency distribution or trading readiness.

The next step measures a real private SQLite reservation commit, with no signer
or sender. The fixed isolated sibling is:

`$HOME/solana-radar-devnet-rehearsal-unsigned-admission-rehearsal-v1`

It contains `rehearsal.admission.sqlite` with private raw unsigned evidence. It is
separate from the operational `-entry-handoff-v1` slot, which remains vacant.
The existing signing/submission tools cannot select this rehearsal directory.
Rehearsal commitments are not an operational allocator and must never be counted
as either wallet-wide holds or newly spendable funds. Waiting for a host review
necessarily outlives the evidence; that is why this first disk rehearsal does not
consume the operational slot.

## Atomic boundary and failure behavior

The command makes one bounded collection, at most 20 devnet RPC requests including
one unsigned simulation. It preserves the original minimum deadline and has no
retry, key access or send capability. Public reports are not accepted as raw inputs.

After collection, it reacquires the cooperating source lock and rereads the source.
It creates the separate private journal, then starts one write transaction. Raw
prices, deployment, instruction bytes, balances, simulation and the full entry/exit
fee policy are revalidated. The reservation event and its raw capture are inserted
in that same transaction. Source state is reread, and STOP, source identity,
wall-clock expiry and the monotonic budget are checked before COMMIT.

- Failure before COMMIT rolls back both the reservation event and capture table.
  An initialized empty journal may remain; it is preserved as incomplete.
- A late COMMIT cannot be undone after it returns. The tool retains the reservation
  and reports `unsigned-rehearsal-recorded-unusable`, without an on-time claim.
- An ambiguous commit reports `rehearsal-inspection-required` with an unknown
  reservation outcome. Read-only status resolves what is actually stored.
- An existing operational or rehearsal slot blocks a new attempt before RPC.
  There is no reset, refresh, automatic retry, release or conversion into signing.
- Status uses read-only SQLite, rejects recovery sidecars, validates the stored raw
  capture against the reservation and never makes a network request. Expiry or STOP
  does not erase the historical commitment. Corrupt or partial storage remains
  explicitly unavailable. Recovery cannot establish the exact disk commit time.

The source lock cannot prevent unrelated external wallet activity. Local owner
trust remains part of the design. A checksum is not protection against replacement
of all private evidence by a malicious owner. No mainnet or profit claim follows.

## Validation

109 targeted local tests passed across admission, locked source binding, signer
handoff, timing, journal/read-only behavior and the new rehearsal. The new portable
host exercise has 22 cases. They cover atomicity, explicit opt-in, source/STOP/
expiry/clock/monotonic changes, storage failure, a late commit, a lost commit
acknowledgment, corruption, duplicate attempts and read-only recovery.

A full-source test drove the actual collector/parser stack over fake RPC responses,
kept all five source reads and seven verifier processes, wrote the isolated
reservation, then replayed it after expiry without changing source or journal bytes.
Fault injection is not proof against every power-loss/filesystem failure. Hot
recovery files are preserved and refused by status, not repaired automatically.
The November 2 Kali run accepted this gate: 1,754 ms remained after the
664.565 ms reservation stage; read-only recovery matched the complete reservation
and original deadline with no RPC requests. This is one sample, not a latency guarantee.

## Kali acceptance

Fetch the exact branch and commit supplied in chat. Run the default CLI first:

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/position-book/durable_admission_cli.py" \
  --output "$PWD/radar-durable-admission-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expect 22 cases passed. Then run **one** `--action prepare` with the explicit
`--allow-local-rehearsal` flag and the existing wallet/pool plus the two-exit-attempt,
10,000-lamport per-exit / 30,000-lamport total scenario. This creates private local
storage. It does not spend tokens or SOL, sign, submit or reserve operational funds.

After any prepare attempt, use `--action status` with the same source, wallet and
pool. Do not pass the write opt-in or fee options to status. Do not rerun prepare,
delete a directory, clear STOP, replace source or upload the private journal.
The chat release includes complete commands for both actions.

Upload the three public `.json.gz` reports. A successful prepare is
`unsigned-rehearsal-recorded` with `commitCompleted=true` and
`commitOnTimeObserved=true`. Later status may say `unsigned-rehearsal-expired`;
that is expected historical retention, not a reason to retry. A failed or late
prepare is evidence to investigate, not permission to extend freshness limits.
No scanner rebuild or service restart is required.

## Next gate

The actual host commit and read-only recovered identity passed. PR #70 consolidated
this batch after all ten CI groups passed. Next validate the
[fresh signing integration](FRESH-SIGNING-INTEGRATION.md). That future path requires fresh evidence,
new checks at signing/submission, exact acknowledgment recovery, delayed exit and
closed accounting. The isolated rehearsal ledger stays historical.
The November 3, 5 and 6 availability-study capture schedule is unchanged.
