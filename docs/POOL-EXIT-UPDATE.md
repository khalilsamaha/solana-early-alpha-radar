# Pool, timing and fixed-exit evidence update — 11 October 2026

Requires the deployed scanner source from commit `fdf7199e3391f04ae7b179aef46f2236b511ec20`. This is an evidence update, with no change to scanner 0.2.9 signal rules, quote observer 0.6.0, request limits or notifications.

## What changes

Only `src/core/fast-shadow.js` changes in the production scanner. Each active Fast30 position retains up to eight recent valid observations plus its first alternate-pool observation. Data are attached to existing checkpoint events; there are no new per-poll SQL writes, external calls or subscriptions. Event bytes increase by a bounded amount. Incomplete paths are labeled partial after restart. Original-pool prices, missing classifications and return calculations remain unchanged.

The offline report adds separate alternate-pool checkpoint evidence and backward-only price comparisons. It selects only original-pool responses already recorded before a quote request, no more than 20 seconds old, and exposes the actual age and whether it is within five seconds. These are not simultaneous prices or measured slippage. Historical reports have no new trajectory and remain explicitly unavailable.

A persisted `fixed-short-exits-1` protocol starts at the first new Fast30 entry after activation. Its primary exit observation is 30 seconds after the hypothetical buy response; 60 and 120 seconds are fixed comparators. A quote request over five seconds late remains separate from on-time statistics. Failed, pending, missing and invalid exits retain full denominators. Additional 0%, 1%, 3% proceeds haircuts are stress scenarios, not measured trading fees. Old observations remain exploratory for this new protocol, even when forward for the earlier entry-feature test.

The quote observer remains unchanged. Existing quote sampling is reused. No automatic trades or best-exit selection are introduced.

## Deploy

Use the exact reviewed commit supplied with the release. The development checkout and running host project are different directories. Do not run Compose from `scanner/`.

```bash
cd ~/apps/solana-radar-dev
git fetch origin feature/pool-exit-evidence-20261011
# Check out the exact commit supplied with this release before continuing.

python3 deployment/install-pool-exits.py \
  --project "$HOME/apps/solana-early-alpha-radar" && \
cd ~/apps/solana-early-alpha-radar && \
sudo docker compose up -d --build --force-recreate radar
```

The installer rejects unexpected source/dependency hashes and symlink targets, runs scanner tests against a staged copy, makes a dated source backup and changes one source file. It does not copy `.env`, Compose or databases. The restart can interrupt active research paths, which remain explicitly marked.

## Verify

```bash
cd ~/apps/solana-early-alpha-radar
node --env-file=.env \
  ~/apps/solana-radar-dev/deployment/verify-pool-exits.mjs
sudo docker inspect \
  --format 'StartedAt={{.State.StartedAt}} RestartCount={{.RestartCount}} Status={{.State.Status}}' \
  "$(sudo docker compose ps -q radar)"
```

Expect `ready: true` and `pathEvidenceVersion: pool-timing-evidence-1`. The exit registration can be null immediately after startup; it is created with the first new Fast30 entry. Do not restart just to force it.

After new entries complete their five-minute paths:

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/quality-tools/run-evidence.sh --hours 12
```

Upload both generated files. Correctness can be checked after a few completed paths; strategy assessment depends on forward quote observations and their failures, not elapsed hours alone. Earlier Fast30 and entry-shadow summaries remain available and unchanged.

## Rollback

Use the exact source-backup directory printed by the installer:

```bash
python3 ~/apps/solana-radar-dev/deployment/install-pool-exits.py \
  --project "$HOME/apps/solana-early-alpha-radar" \
  --rollback /absolute/path/printed/by/the/installer
cd ~/apps/solana-early-alpha-radar
sudo docker compose up -d --build --force-recreate radar
```

The rollback placeholder is not a literal path. The guard requires the corresponding backup manifest and unchanged post-install source. Stored evidence is not deleted by rollback. Use each earlier update's pinned checkout if deploying that earlier update; old installers verify their own payload hashes and are not installers for later source.

## Review boundaries

This change is stacked on the evidence-diagnostics branch, which itself depends on the Fast30 follow-up branch. Merge dependencies in order and retarget subsequent PRs deliberately. Deployment by pinned commit does not merge a PR. See `PROJECT-HISTORY.md` for the complete project record.
