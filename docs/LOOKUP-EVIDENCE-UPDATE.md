# Lookup evidence and reboot recovery — 18 October 2026

## Verified input and scope

The Kali report captured on 17 October at 21:54:25 UTC replays exactly. Its v0 devnet transaction has one required signature and two lookup descriptors. Signed bytes and JSON agree; the endpoint reports finality. No transaction was sent. The public capture is retained as `recorded-chain/devnet-two-table-fixture.json`; it contains public transaction evidence, not a wallet key.

This release adds a separate read-only lookup audit. It re-verifies the supplied transaction, derives table keys and indexes from signed bytes, then makes at most three public reads: genesis, one `getMultipleAccounts` request, genesis. Accounts are requested at finalized commitment with `minContextSlot` set to the transaction slot. There are no retries, alternative transaction selection, credentials, signing, sending or ledger updates.

It validates table ownership, non-executable account state, canonical base64, bounded layout, state discriminator, authority option, metadata bounds, index bounds, and the complete writable/readonly address order against the transaction's reported loaded addresses. Up to 32 unique tables and 256 addresses per table; raw account bytes and their context are preserved for offline replay.

## What a successful result means

`current-lookup-addresses-consistent` means the separately fetched RPC account bytes resolve the signed indexes to the same addresses as the earlier transaction metadata. It does **not** mean independently authenticated chain state or exact historical availability. Both responses come from the same endpoint. `historicalStateProven` and `executionApproved` remain false.

`minContextSlot` is a lower bound, not a historical account query. A table extended after the transaction leaves its historical availability unknown. Same-slot use of a newly extended index is explicitly incompatible. Deactivation before the transaction leaves historical status unknown because this reader does not reconstruct historical SlotHashes. Missing/closed accounts remain unknown. Wrong owner, different addresses, out-of-range indexes and inconsistent contexts are explicit failures. No uncertain result is silently promoted to success.

The existing signed intent journal still rejects ALT-bearing messages. No source or behavior changes to the scanner, observer, signal rules, research protocol, backups, budgets or ML. No container rebuild or service restart is needed.

## Run on Kali after checking out the pinned release commit

```bash
cd ~/apps/solana-early-alpha-radar
python3 -E -s ~/apps/solana-radar-dev/recorded-chain/lookup_cli.py \
  --live \
  --input "$PWD/radar-recorded-chain-20261017T215423Z.json.gz" \
  --output "$PWD/radar-lookup-check-$(date -u +%Y%m%dT%H%M%SZ).json.gz"

bash ~/apps/solana-radar-dev/deployment/reboot-check.sh
```

Upload both printed output files. Do not rerun to select a favorable outcome. The lookup report is private (0600), atomically created and never overwrites an existing file. The recovery script requires sudo for read access; it makes only a loopback readiness request and does not read secrets or contact cloud services.

Offline replay, with an actual saved lookup-report filename:

```bash
python3 -E -s ~/apps/solana-radar-dev/recorded-chain/lookup_cli.py \
  --replay /absolute/path/to/radar-lookup-check.json.gz \
  --output /absolute/path/to/radar-lookup-replay.json.gz
```

## Reported reboot outage

At 23:58 Amsterdam on 17 October, the user reported approximately three hours offline due to a system reboot. Exact start/end and post-reboot recovery remain unverified. The recovery script captures local timestamps, boot history, scanner container state/readiness, observer polling and the configured services/timers. Previous boot last-log time is not necessarily shutdown time. Healthy now does not prove uninterrupted operation.

Keep pre-outage, interrupted and post-recovery observations distinguishable in the next review. A missing observation is not a zero return or proof of no opportunity. Do not reset the forward registration, recreate ledgers, clear interrupted watches, restore an old database or alter collection quotas. This release records the incident in project documentation and collects recovery evidence; it does not retroactively annotate every historical row or determine the exact outage interval. Quotes already complete before the interruption remain usable subject to existing protocol guards. Crossing windows require their actual evidence and interruption status to be examined.

## Next engineering gate

Review the host lookup and recovery reports. Develop a narrowly scoped devnet workflow with a prior registered intent, isolated signer, simulation, bounded authorization and reconciliation, initially using a simple message without lookup tables. ALT execution remains blocked until its own admission requirements are satisfied. Strategy validation remains independent; no funded pilot or model activation is authorized by this audit.

Primary references: [getMultipleAccounts](https://solana.com/docs/rpc/http/getmultipleaccounts), [lookup program state and activation rules](https://docs.rs/crate/solana-address-lookup-table-program/1.14.17/source/src/state.rs). The implemented format is the 56-byte metadata layout with at most 256 addresses; unknown layouts fail explicitly.

## Development observation

A three-request capture for the same public transaction resolved all 14 referenced addresses
consistently at account context slot 512218051. One table's last extension (512217904) was
later than the transaction (512215867). The result correctly reports current address
consistency **and** unknown historical availability. Saved public account bytes are replayed
in tests; no historical state was invented. Development used the environment's standard
HTTPS proxy route (recorded in provenance); the shipped CLI disables environment proxies.
