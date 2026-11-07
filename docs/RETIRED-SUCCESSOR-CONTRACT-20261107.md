# Unsigned successor contract after an exit retirement

The November 7 retired-exit review passed eight read-only requests, with no evidence or budget blockers. It preserved 998 acquired atomic units, 500000000 protected units, and 25000 held fee lamports. The original expired signature remains retired. Absence of a signature in provider history is not treated as proof that it never executed.

This increment implements a separate unsigned successor record, plus lifecycle and snapshot replay. It does not connect a live collector, signer or sender. Its only operator CLI runs offline checks using disposable synthetic journals; it accepts no wallet, private directory, transaction or provider input.

PR #78 was merged after all 12 GitHub checks passed. The tested source tree is on main at `d1153636db104295b9a8812565a1db17b1e47738`. This increment builds on that consolidated tree.

## Contract

- Bind the successor to the exact retired preparation, retirement record and fully replayed source context.
- Preserve all previous journal rows and backend acknowledgement files. The original preparation reader still returns the retired generation.
- Recheck the original signature, expiry and all five scoped accounts, then validate the complete fresh quote, simulation, instructions and collection provenance.
- Require a distinct blockhash and the original quantity and protected inventory.
- Charge the retired signature as one consumed attempt. The candidate is attempt two under the original cumulative limit, not a reset allowance.
- Preserve the full fee hold, including the retired attempt's unresolved exposure. Creating the unsigned record adds no allocation and releases nothing.
- Hold the source lock and SQLite writer reservation across replay, producer work and atomic publication. Recheck backend files, STOP, deadlines and freshness before commit.
- Duplicate calls replay the same record without recollecting or renewing its deadline. An expired record stays expired and held.
- Roll back incomplete publication. If output is lost after commit, replay discovers the committed record without another producer call.
- Reject malformed, orphaned or rehashed-but-semantically-invalid records. Existing sender guards continue to reject the retired attempt.

The producer function is an internal contract exercised only by synthetic tests. A public report cannot be imported as signing evidence. The new record is not recognized as an active preparation by the old signer or sender.

## Host check

After checking out the exact published feature revision:

```bash
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/retired_exit_successor_cli.py" \
  --output "$PWD/radar-successor-contract-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

No Docker rebuild or service restart is required. Upload only the generated public report. Do not alter or delete private journals, and do not rerun the retired sender.

## Next integration gates

1. Connect a fixed, bounded, read-only devnet collector inside this source lock. Measure end-to-end freshness on Kali without signing.
2. Add an explicit successor signing generation bound to this record and the cumulative reservation. Preserve the old backend files and permanent retired-sender denial.
3. Rehearse one-send recovery and receipt accounting before any controlled devnet execution.

These engineering gates do not establish a profitable strategy or authorize a real-money pilot. Research and scanner settings remain unchanged.

## Validation for this increment

- 12 offline successor cases passed with network connection attempts disabled.
- 56 affected retirement, replanning, snapshot, lifecycle and recovery regression tests passed.
- Four CLI checks rejected live-source/execution arguments and preserved an existing output.
- Two CI partition tests and tracked-source/package-manifest hygiene passed.
- No live collector, wallet or private user journal was exercised. Kali offline acceptance remains the next operator check.
