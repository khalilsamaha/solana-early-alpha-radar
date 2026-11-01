# Entry admission timing observation — November 1, 2026

After the accepted balance, closure and lifecycle batch, the next engineering
question is whether fresh entry evidence can survive real collection and local
admission replay within its original expiry. This increment measures that path
without creating a live admission, signing boundary or transaction.

## One bounded observation

The opt-in command uses the existing fixed controlled devnet wallet/pool scope
and October 27 deployment observation. It performs at most 20 RPC requests,
including one unsigned entry simulation, with no retry. It does not alter the
pinned program observation when bytes change. A different deployment is a failed
observation requiring review, not permission to trust new bytes.

The collector passes private raw evidence directly in process. Public reports
are never accepted as inputs. After collection, the cooperating wallet lock is
reacquired and held across the following sequence:

1. Refuse any existing admission sibling directory, including partial state.
2. Re-read the closed source and compare its full scoped reservation identity.
3. Replay the exact raw price, message, deployment, balances, simulation and
   entry-plus-exit-fee funding through the existing admission validator.
4. Re-read source identity, check STOP and the admission slot again, then check
   the original wall-clock expiry and the 30-second monotonic observation budget.

The effective expiry is the earliest **existing** collector preflight, binding
and cost deadline. No timestamp is rewritten. The raw validator must return the
same cost deadline. A slower validation or final source read cannot turn expired
evidence into a pass. No signing, disk commit or future exit work is hidden in
reported headroom: those remain separate measurements and acceptance gates.

An existing admission stops observation before RPC. If one appears during
collection, it remains untouched and the result is unavailable. STOP, changed
source identity, invalid budgets, unknown reservations, missing raw handoffs,
collector failures or clock regressions also prevent success.

## Public output

The report separates time spent checking the local slot, collecting the entry,
reading locked source state before/after validation, and validating raw admission
evidence. Successful reports show original-deadline headroom and hashes plus
projected principal/fee commitments. Failure reports retain the stage, bounded
diagnostic, request count and available timings. Unknown measurements remain
null. Raw packets, simulation account data and private keys are not exported.

`entry-admission-timing-consistent` means this one no-write path finished on time.
It does not establish current wallet-wide solvency, durable reservation success,
private signing latency, send/confirmation latency, future exit feasibility,
complete round-trip funding or mainnet profitability. The local source lock
cannot block unrelated external wallet activity. This is not a runtime poller.

## Local validation

Eight focused tests passed, including the 19-case portable exercise, the actual
20-request collector/parser stack over fake HTTP, RPC failure without retry,
changed source state, validation expiry, stricter original binding deadlines,
new partial admission state, missing raw evidence and private/exclusive CLI
publication. The portable exercise rejects calls to sockets, signing and the
admission writer, and compares unchanged source fixture bytes.

## Kali checks

Fetch the pinned development commit supplied with the release. Run the offline
checks first. The lifecycle exercise now includes a durable ledger STOP as well
as the STOP file (24 cases); the timing exercise has 19 cases:

```bash
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/admission_lifecycle_cli.py" \
  --output "$PWD/radar-lifecycle-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"

python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/admission_timing_cli.py" \
  --output "$PWD/radar-admission-timing-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Then make **one** opt-in observation using the existing devnet rehearsal directory,
wallet and pool. The 2-attempt/10,000-lamport exit cap and 30,000-lamport total below
are a bounded observation scenario only; the command reserves and spends nothing:

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
  --output "$PWD/radar-admission-timing-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Upload all three public reports. `unavailable` exits with code 2 but still publishes
its diagnostic report. Preserve it; do not repeat observation merely to obtain a
pass. Do not delete an existing admission directory if the slot is occupied.
There is no service restart, scanner rebuild, airdrop or private-key operation.
Live host timing remains pending until the resulting report is reviewed.

## Next gate

Use measured stage durations and failures to decide whether the admission path
needs optimization or can progress to an explicitly scoped durable rehearsal.
Do not relax freshness limits or infer signing/submission readiness from this
read-only pass. Next steps remain separate entry/exit execution, failure recovery,
closed accounting and only then a narrow mainnet design and funded pilot scope.
The availability study and November 3, 5 and 6 preservation schedule are unchanged.
