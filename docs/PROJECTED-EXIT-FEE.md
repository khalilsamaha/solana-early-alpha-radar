# Projected exit fee and conditional funding — 30 October 2026

## Accepted predecessor

The October 30 04:16 UTC host reports passed ten portable offline cases and the
projected reverse-message observation. The public report binds entry 1,000 → 998
to a reverse draft using exactly 998 atomic units, projected output 997 and
minimum 988. The collector used 20 requests, one unsigned entry simulation and
8.015 seconds inside the original ten-second deadline. Closed ledger identities
remained unchanged. Summary hashes, public account mapping, baseline, quantities,
clocks and approval flags were checked; raw RPC bytes were not in the upload and
were validated on the host. This establishes neither an exit fill nor an edge.

## New increment

`position-book/projected_fee_cli.py` adds an explicit standalone mode. It requests
`getFeeForMessage` for the exact independently decoded reverse message, with
finalized commitment and a minimum context slot equal to the entry simulation's
slot. The transport arms precisely those parameters after the original 20 calls;
only that fee read and a final devnet genesis check may follow. No additional
simulation, retry, signing, sending or journal update is supported.

The fee is not copied from entry or attached to an executable packet. A null,
non-integer, boolean, zero, negative, over-cap or old-context fee is unavailable.
Wrong message parameters, wrong cluster and inconsistent clocks also fail.
The reference blockhash is unchanged; a fee response does not authorize later
submission or assert future blockhash validity.

After fee collection, the reader replays the closed local reservation view under
the same lock, compares ledger/cycle identities, and revalidates the raw parent,
message and cost evidence. The final review must still finish inside the original
**ten-second quote deadline** and **30-second shared transport budget**. The new
mode permits at most **22 requests**. Existing observers keep their old limits.

Conditional funding uses:

- Observed fees: independently observed entry fee plus exact reverse-message fee.
- Required native caps: entry cap plus exit cap, without adding the observed fees
  again. Each cap already includes the validated priority-fee treatment.
- Available native balance: the verified entry prestate minus known local holds.
- Remaining after caps: that available balance minus both caps.

No rent or separate tip is added because these exact validated messages only use
existing standard SPL accounts and contain no account creation/tip instructions.
Embedded token swap fees are reflected in the output; they are not SOL fees.

`conditionalCapCoverage: true` only means the snapshot can cover both declared
caps under those assumptions. `roundTripFundingEstablished`, execution approval,
actual entry execution and exit simulation stay false. Failed-attempt budget,
wallet-wide reservations, external-wallet exclusivity and native/token valuation
remain unavailable. No durable spending capacity is reserved by this command.
The public report contains amounts, slots, clocks and hashes; message wire stays
in memory and only the serialized message is sent to the fee RPC.

## Local validation

All **216 position/accounting tests** passed, including nine new fee tests. The
portable command passed **11 offline cases**. Tests cover exact message/context
binding, fees differing from entry, invalid/null fees, cap shortfalls, unchanged
default request limits, explicit transport arming, late responses, changed local
journals, stop requests, private exclusive outputs and absence of signer calls.
Source hygiene and whitespace checks passed. Live host acceptance is pending.

## October 30 timing correction

The first host fee report at 04:37 UTC was **unavailable**, not accepted. It
completed 22 requests but withheld `projectedExitFee` when final review exceeded
the original quote deadline. The last local reservation read ended at 04:37:09.385
UTC, only 401 ms before the exclusive 04:37:09.786 deadline. The report was captured
at 04:37:10.367; it must not be interpreted as a fee/funding pass.

The correction validates a private deep-copied raw snapshot once per phase and
reuses it for the projection, draft and fee consumers. A new raw review is created
at final reservations/time; nothing is cached across observations. Returned
summaries/drafts are copies, wire semantics are checked each time, and public raw
entry points still validate their supplied evidence. No public report can create
a trusted private review. Instrumented tests require two parent reviews and four
cost reviews for the integrated fee path, rather than repeating parent review for
every consumer.

The report now identifies `validationMode: per-snapshot-parent-review-1` and
includes bounded `timing` fields for parent validation, fee collection, final
reservation read, final validation and completion. A failed final deadline check
retains negative/zero remaining time while withholding all final fee/message
approvals. The 22-request cap, 10-second quote deadline, 30-second transport budget,
stop checks and final locked journal reread are unchanged. Host acceptance is
still required; lower duplicate work is not a promise about RPC latency.

Correction validation: **221 full position/accounting tests passed**, including
five added cases for review-count bounds, snapshot/output isolation, equality
with raw review, repeated wire validation and late-completion withholding. The
portable offline check still passes all 11 cases. Source hygiene and whitespace
checks passed; no new host success is claimed by these local checks.

## Kali check

After selecting the published feature commit:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
radar_cli="$HOME/apps/solana-radar-dev/position-book/projected_fee_cli.py"
python3 -E -s "$radar_cli" \
  --output "$PWD/radar-projected-fee-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
python3 -E -s "$radar_cli" \
  --simulate-devnet --deployment-observation-20261027 \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-projected-fee-live-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

Expected: `offline-checks-passed` (11 cases), then
`controlled-projected-fee-observation-consistent`. Upload both public reports.
An unavailable report is useful evidence; preserve journals and do not widen
limits or invoke execution to bypass it. No rebuild or restart is required.

## Next gate and unchanged scope

After host fee acceptance, consolidate the conditional evidence contract before
connecting it to a supported sequential rehearsal. Public entry simulation does
not commit acquired inventory, so independently simulating an exit against the
old pool is not evidence of this round trip. Actual sequential evidence needs a
supported stateful rehearsal or a separately scoped controlled cycle.

Scanner monitoring, notifications, quote sampling and the frozen availability
confirmation remain unchanged. Mainnet route validation and strategy qualification
are separate gates; no real-money pilot or revenue claim follows from this check.

RPC reference: https://solana.com/docs/rpc/http/getfeeformessage (checked October 30,
2026). The method accepts a base64 message and returns a fee or null at a context
slot; it does not execute the message.
