# Prepare the next controlled devnet cycle

The first controlled entry and reverse already occupy `swap-execution-v1` and `swap-reverse-v1`. They must remain durable history. This release prepares a separately identified `controlled-cycle-0002` without renaming, resetting, copying or deleting any existing wallet or execution journal.

It is a preparation milestone. The new record cannot sign or submit and is not yet accepted by a sender. The next integration must bind this identity and cumulative allocation at the signing and submission boundaries, with fresh transaction/program/account checks. Do not replay the first cycle to exercise the new guard.

## What preparation establishes

1. Replays both exact signed historical receipts and the original controlled-pool setup locally. The prior round trip must be finalized, successful, closed and have zero residual acquired quantity.
2. Checks any existing historical position book and prospective spending journal agree with those receipts. It does not reconcile, erase, backdate or silently repair them.
3. Makes at most seven read-only requests to the fixed devnet endpoint: genesis before/after, each signature's finalized status and exact transaction, and a single finalized wallet/token-account snapshot.
4. Confirms the wallet and both token holders still match the closing receipt. Unexpected balance changes, delegate/close authority changes, stale local observation timing, wrong cluster or unavailable/mismatched receipts stop preparation. This is a strict continuity test, so even an intervening legitimate airdrop requires explicit investigation.
5. Writes an exclusive private preparation record and completion seal under the existing execution lock. Repeating preparation returns the saved state without network access or a second allocation. A crash after directory creation remains incomplete and cannot silently restart.

The record includes bounded private chain evidence and hashes of the source evidence. Public reports omit transaction bytes and keys. Same-user file ownership and the public RPC provider remain trust boundaries; the hashes are not protection against an owner deliberately rewriting the files.

## Fixed two-cycle scope

| Measure | Policy |
| --- | --- |
| Controlled cycles covered | Prior cycle plus one proposed subsequent cycle |
| Cumulative gross entry input | At most 2,000 atomic units of the original test mint |
| Proposed subsequent input / minimum output | 1,000 / 990 atomic units |
| Subsequent round-trip fee allocation | 20,000 devnet lamports |
| Cumulative swap fees including proposed allocation | At most 40,000 devnet lamports |

With the previously verified 10,000-lamport round-trip fee, the cumulative fee allocation is 30,000 lamports. Returned tokens do not replenish the gross-input cap. Background token holdings are not counted as a new position. Native fees and token units remain separate. Pool setup, rent and unrelated wallet activity are excluded from this narrowly defined swap budget.

The allocation is not a signer-enforced reservation yet: reports explicitly say `pretradeBudgetEnforced: false`, `senderConnected: false`, and `executionApproved: false`. The earlier spending guard enforces one cycle in its existing sender; this preparation provides the preserved identity and cumulative context needed to integrate the subsequent cycle correctly.

## Kali commands

Fetch and detach at the exact release commit supplied in chat. Then run the offline self-check:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/devnet-pool/cycle_cli.py" \
  --output "$PWD/radar-cycle-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

Expected with the balance-diagnostic update: `offline-checks-passed`, 24 cases (the original 18 plus six diagnostic cases). It uses disposable unfunded keys and synthetic RPC, never your existing wallet or the public network.

After that passes, prepare using the existing dedicated devnet identity:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/devnet-pool/cycle_cli.py" \
  --action prepare \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-cycle-preparation-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

Expected: `prepared-not-executable`, seven read-only requests on first success, no signatures or submissions. The tool reads public wallet metadata, never `signer.pk8`. Upload only the named public reports. If stopped, provide its bounded reason and preserve all files; do not clear journals, alter balances or run old execution commands to get around a refusal.

`--action status` with the same scope and a new output path replays saved local evidence with zero network requests. It does not refresh balances. If preparation was interrupted, a partial directory stays blocked for investigation.

## What remains unchanged

No scanner rebuild, observer restart, background service, backup change or private-key migration is needed. The frozen study remains fixed, with its next user review scheduled for October 27. This release includes the existing collection tools. Research sample-size/date-coverage gates and empirical quality criteria still apply; another elapsed day does not automatically approve a model or real-money trial.

After the host preparation report is reviewed, integrate the separately identified cycle into the restricted signer and one-send recovery flow. That release must account for the recorded prior spending and retain any uncertain new reservation. A real devnet demonstration of that integration is still required; this preparation does not claim it has occurred.

## Diagnose a balance-continuity refusal

The first supplied host self-check passed all 18 original cases, while live preparation stopped at `wallet-balance-changed-since-close`. This check happens before creation of the next-cycle directory. The error establishes a native balance mismatch, not its size or cause; token continuity checks had not yet completed. It does not establish that an airdrop, fee, unauthorized transfer or accounting error caused the difference.

The new `diagnose` action revalidates the original receipts and compares a fresh finalized three-account snapshot, using at most seven read-only requests. It exports expected/observed balances and signed differences in native lamports and test-token atomic units, plus token-authority status. Devnet SOL differences are formatted with exact decimal arithmetic. It does not enumerate intervening transactions or claim attribution.

After checking out the pinned diagnostic release, run:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/devnet-pool/cycle_cli.py" \
  --action diagnose \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-cycle-balance-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

`balance-comparison-mismatch` is a completed diagnostic, not permission to prepare or execute. `balance-comparison-match` only describes that snapshot and is also not execution approval. Upload the public report. Preparation continues to require exact continuity and sufficient funds. There is no balance override, rebase, funding request, signing, new cycle directory, or change to old journals. The diagnostic remains usable with `STOP` present because it cannot spend or create a preparation. It refuses malformed, stale, wrong-chain or conflicting receipt evidence rather than exporting a trusted comparison.
