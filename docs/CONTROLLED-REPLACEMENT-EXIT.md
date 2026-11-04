# Controlled replacement exit — November 4, 2026

PR #74 consolidated the replacement contract after all twelve CI groups passed.
This development increment builds on main `9ca61a5077830f226c9aa51230af4d254a718c53`.

The connected replacement host report passed twelve integration checks and ten
independent signer-contract cases at 04:23:09 UTC. The original controlled devnet
exit remains unconfirmed; these synthetic checks did not operate on that position.

`position-book/controlled_replacement_cli.py` adds a narrow command for the tested
internal replacement function. Default `check` runs seven command-boundary checks
without a wallet or network. Explicit `execute` requires the original preparation
hash, the dedicated wallet/pool/directory and all three separate opt-ins. There is
no endpoint, private-key path, fee-policy replacement, imported report, retry,
clock override, queue or automatic follow-up argument.

The underlying function rechecks the private journals before collection and before
persistence. It refuses existing replacements, signing records, backend markers,
STOP, wrong ownership or changed source state. It preserves the old preparation,
uses a newly collected blockhash and retains its original deadline through signing
and the one-send boundary. The command adds no deadline extension or fee increase.
The source and fixed handoff directories cannot be used as public report targets.
Reports are exclusive mode-0600 files. An exception after commit or a missing report
never establishes rollback and never starts another attempt.

## Local validation

Seven command tests passed, including the full connected replacement rehearsal
through this new routing layer (twelve integration checks and ten independent
signer cases), repeated-execution refusal, exact opt-ins, safe report projection,
exclusive output and publication failure. Two partition tests and source hygiene
also passed. The new command test is explicitly assigned to partition 0 to avoid
adding load to the formerly timed-out group. These tests do not contact the user wallet or a real RPC endpoint.

## Host procedure

Use the pinned development commit supplied with this release. Run the offline
command check, then inspect the current preparation with the existing read-only
`exit_preparation_audit_cli.py --action inspect`. The known original preparation
from the November 3 06:44:29 UTC report is:

`2c9f7a454ebc94387dedeb6a3c2d6dc4f06d256eb1b4fa82743dbb3d216d1b13`

The original report showed 998 owned acquired atomic units, 500,000,000 protected
inventory units, and 25,000 lamports still held. These are historical observations,
not assumptions about current balances. Execution reads current evidence itself.
It cannot accept a new hash automatically from the public report.

For the one explicitly requested controlled devnet replacement, invoke:

```bash
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/controlled_replacement_cli.py" \
  --action execute \
  --allow-unsigned-replacement \
  --allow-private-key-signing \
  --allow-devnet-submit \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --expected-preparation-sha256 2c9f7a454ebc94387dedeb6a3c2d6dc4f06d256eb1b4fa82743dbb3d216d1b13 \
  --output "$PWD/radar-controlled-replacement-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Run once. Acknowledgment returns zero only within the original deadline; uncertainty,
late completion and refusal return nonzero. Neither exit code authorizes a retry.
Keep all journals and public reports. No Docker rebuild or service restart is needed.
This command can sign and submit one devnet transaction; the offline check cannot.

## Recovery and next gates

After the attempt, inspect using the existing controlled acceptance `status` action.
If signing acknowledgment was lost, `recover-exit-signature --allow-reconcile`
reads the existing acknowledgment without signing. For an existing send boundary,
`settle-exit --allow-reconcile` observes its recorded signature and reconciles the
receipt; it never submits another transaction. `close-exit --allow-reconcile` is a
separate action after the receipt is accepted, with fresh residual balance checks.
An unsigned failed replacement has exhausted this one-replacement path and needs
inspection; it is not permission to delete or reset evidence.

Scanner, quote observer, monitoring, notifications and availability-study rules
are untouched. Actual finalized exit receipt, scoped accounting and closure remain
host acceptance gates. Mainnet execution and strategy profitability remain outside
this release.
