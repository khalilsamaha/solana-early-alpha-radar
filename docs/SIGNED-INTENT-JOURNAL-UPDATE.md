# Signed intent identity and restart recovery — 17 October 2026

The preceding host intent self-check passed all six expected cases at 16:49 UTC. It checked hypothetical transaction balances against a declared message, but did not verify signatures or persist an intent. This release adds those missing layers in a separate offline journal.

The new verifier checks every Ed25519 signature against exact serialized legacy/v0 message bytes, then binds the signed identity to the prior intent contract. The journal records intents atomically, rejects conflicting retries, records a one-time submission boundary and preserves unresolved outcomes after process restart. Supplied receipt reconciliation can mark a consistent final result, a fee-only failure or sticky quarantine. No outcome grants trading permission.

No production scanner, observer, scheduler, quote budget, signal rule, model, protocol registration, notification or backup changes are included. No rebuild, restart, Python package installation, wallet connection, funding or private key is needed. Python 3 and Node 24 are already available on the host.

After fetching and checking out the exact commit supplied with this release, run:

```bash
cd ~/apps/solana-early-alpha-radar &&
python3 -E -s \
  ~/apps/solana-radar-dev/intent-journal/intent_journal_cli.py \
  --output "$PWD/radar-signed-intent-check-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

Expected: `Signed intent journal: 11`, followed by the upload path. The report must say `mode=synthetic-offline`, `casesPassed=11`, `temporaryJournalRemoved=true`, `networkRequests=0`, `executionApproved=false`, `resubmitAllowed=false`, and `productionLedgerUpdated=false`.

Existing/create/close/v0/multiple-signer receipts and later recovery should reconcile; a finalized failed transaction should be fee-only; duplicate boundaries and tampered wire should be rejected; unexpected wallet debit should be quarantined. These are synthetic tests with real cryptographic signature verification, not real chain transactions.

## Scope and next sequence

1. Validate this release on the Kali host with the command above.
2. Add a reproducible **recorded-chain** fixture path, compare raw signed bytes with RPC JSON and reconcile the exact supported transaction. Independently establish cluster identity; support lookup resolution before claiming coverage for ALT-based aggregator transactions.
3. Exercise a separately scoped devnet workflow with verified intent ordering, failure recovery and reconciliation. Signer isolation, simulation, exposure limits, independent stop/exit controls and supported router/account layouts are still needed before any funded workflow.
4. Continue the registered forward study unchanged. The latest reviewed market capture still contains only 166 compatible watches across two UTC days; all fitting guards fail. No new market evidence is supplied by this self-check.

There is no justified real-money test date or profitability claim. Execution correctness and a useful trading strategy are separate gates. This release advances execution identity and persistence while research collection continues.

Full contracts, limitations and optional journal API: [intent-journal/README.md](../intent-journal/README.md).
