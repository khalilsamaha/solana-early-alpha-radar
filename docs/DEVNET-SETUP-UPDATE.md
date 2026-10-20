# 20 October 2026 — setup costs and fresh swap packets

The 12-case swap-rehearsal host self-check and public inventory passed exact replay. That proves the synthetic checks and public observations, not a live swap. The dedicated wallet had 0.00998 devnet SOL and neither reference-pool token. Creating empty accounts alone cannot fund those tokens.

Implemented:

- A read-only controlled test-pair/pool funding estimate with live rent, actual selected AmmConfig creation fee, creation-disabled detection and explicit shortfall.
- Production canonical unsigned CPMM message construction from a prior scope, fresh blockhash and an exact-message fee lookup.
- Same-process handoff into the existing restricted signer/simulation, preserving STOP, durable one-shot state, fee caps, minimum output and independent account/program preflight.
- Tests covering refusal conditions, replay and the real restricted Node signer with synthetic transport and disposable unfunded keys.

Not implemented in this release: creation or minting of the controlled token pair, controlled pool initialization, swap broadcasting, or any funded trading activation. Cost estimates are planning evidence and never authorize spending. No SDK dependencies or production scanner changes are introduced.

## Host action

After fetching the release commit, run this from the production project directory. No sudo, key directory, Docker restart or rebuild is needed:

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/devnet-setup/setup_cli.py" \
  --action setup-costs \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool 3CxsELVbhg3L37ptLm7aihdWoSohUFnJxE3JxdCURFce \
  --output "$PWD/radar-devnet-setup-costs-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

Upload the generated public report. `costs-observed` means the estimate is complete; examine `blockers`, `poolCreationEnabled` and `estimatedShortfallLamports`. It does not mean tokens/pool exist or the wallet is ready. If the pinned deployment has changed or evidence is unavailable, the collector stops instead of switching pool/program or producing assumed costs.

## Next sequence

1. Controlled mint/holder provisioning with precise spend and mint-authority scope and durable receipts.
2. Controlled pool initialization, balance reconciliation and fresh inventory.
3. Actual-wallet signed swap simulation; then separately scoped devnet swap execution and recovery.
4. Continue independent forward strategy validation. Execution correctness alone does not establish an edge or a real-money start date.

Detailed limits and upstream references: [devnet-setup README](../devnet-setup/README.md).
