# Recorded-chain validation — 17 October 2026

The eleven-case signed-intent host report at 17:45 UTC exactly matched local replay. Signature verification, duplicate protection, unknown/restart recovery and quarantine passed their synthetic host checks.

This release adds bounded capture/replay of an existing public Solana transaction. It checks genesis identity before/after collection, explicit finalized status, slot/error agreement, all required Ed25519 signatures and matching raw/JSON message contents. It keeps the projected source capture with its report for independent replay and makes no intent or execution decision.

## What was actually observed

The first selected public devnet transaction was captured with six read requests at 18:11:57 UTC. Its signed bytes verified and matched the JSON message, and both genesis checks matched devnet. It uses one address lookup table. The result is therefore `signed-message-consistent-lookup-unverified`: signed lookup references are verified, but the resolved addresses remain RPC claims.

This observation is beyond generated fixtures, but it is not our own devnet execution, a swap test, a registered intent reconciliation or a profitability result. The development environment required its normal HTTPS proxy route for that capture; the shipped CLI uses direct HTTPS. The exact public capture is retained as an offline regression fixture with this transport distinction. No second transaction was selected to seek a better result.

## Host command

After fetching and checking out the release's exact commit, run:

```bash
cd ~/apps/solana-early-alpha-radar &&
python3 -E -s \
  ~/apps/solana-radar-dev/recorded-chain/recorded_cli.py \
  --sample-devnet \
  --output "$PWD/radar-recorded-chain-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

Upload the `.json.gz` file regardless of whether the result is consistent, unknown, unsupported or mismatch. Provider limits or history availability may prevent a complete check; do not repeatedly rerun it to find a pass. The command reads at most six public responses and sends no transaction. It needs neither sudo nor a wallet, keys, funds, service restart or image rebuild.

The sample may report `signed-transaction-consistent` or `signed-message-consistent-lookup-unverified`. The latter is an explicit coverage gap rather than proof of full lookup resolution. Preserve the report for follow-up. For an entirely offline host check first, replace `--sample-devnet` with:

```text
--input "$HOME/apps/solana-radar-dev/recorded-chain/devnet-recorded-fixture.json"
```

## Next engineering gate

Implement and test bounded lookup-table resolution with clear current-versus-historical state provenance before admitting ALT-bearing transactions to the intent journal. Then design a controlled devnet workflow that records its own intent before submission, with signer isolation, simulation, limits and independent stop/recovery controls. No execution or funded pilot is enabled here.

Production scanner/observer behavior, quote quotas, protocol registration, research models and Backblaze are unchanged. Research collection continues without waiting for this engineering check. The latest reviewed strategy evidence is still the earlier 166-compatible-watch capture; this release adds no market-performance observations.

See [component contracts and limits](../recorded-chain/README.md).
