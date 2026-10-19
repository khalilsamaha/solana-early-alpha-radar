# 19 October 2026 — unsigned direct-swap instruction policy

The supplied position accounting host report (`radar-position-check-20261019T043108Z.json.gz`) exactly replayed all ten synthetic cases. It exercised unknown-outcome holds, failed exits, duplicate protection, fees/loss accounting and stop/quarantine behavior. It did not execute a market position.

The next release adds `swap-contract`: an offline check of raw unsigned direct Raydium CPMM devnet `swap_base_input` messages against a separate policy. It checks the exact ordered account contract and permissions, atomic quantities, minimum output, allowed compute instructions, fee caps, message-bound fee assertion and short local deadlines. It rejects extra instructions, signatures, unsupported token/native/lookup handling and other programs. The source and full scope are in the [component README](../swap-contract/README.md).

This advances pre-signing validation without connecting a signer. The default host check runs twelve synthetic cases, sends nothing and requires no production installation or restart. All matches explicitly leave signing, account state, fee observation, program deployment, cluster, blockhash validity and simulation unapproved/unverified. A fee assertion or account map supplied by the same untrusted transaction builder is not independent evidence.

## Host command

After checking out the published release commit in `~/apps/solana-radar-dev`:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s "$HOME/apps/solana-radar-dev/swap-contract/cli.py" \
  --output "$PWD/radar-swap-contract-check-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
SH
```

Upload the printed public report. Keep the running scanner, observer and research collection operating normally. No keys or database are needed for this step.

## Roadmap position

| Workstream | Evidence now | Next |
|---|---|---|
| Collection and strategy | Existing forward protocol continues; no demonstrated tradable edge | Evaluate new compatible observations under the registered protocol |
| Chain execution | Own devnet self-transfer and atomic WSOL lifecycle finalized and recovered | Verify a narrow swap against independent state, then signed simulation |
| Position accounting | Host synthetic integration passed | Connect a supported devnet entry/exit only after preflight gates |
| Swap instruction contract | Offline validator and adversarial tests built | Host self-check, then read-only state/preflight adapter |
| Funded test | Not approved or scheduled | Complete engineering integration, execution cost/risk checks and separate explicit budget approval |

The direct DEX scope is a validation foundation, not a change to the discovery strategy or a declaration that every Jupiter quote has this structure. There is no requirement to wait another day for this host check. Subsequent engineering can proceed while forward evidence accumulates. No scanner, observer, backups, research rules or trading budget changes in this release.
