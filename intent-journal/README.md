# Signed intent journal 1

Offline engineering component. Verifies public signed transaction bytes and records declared intents in a separate private SQLite journal. It contains no private-key reader, signer, transaction builder, RPC transport or sender. The default command runs synthetic cases in temporary journals and deletes them.

## What is verified

- Exact legacy/v0 message bytes, canonical compact-u16 lengths, transaction size at most 1,232 bytes, header/key/instruction bounds and every required Ed25519 signature. Node 24's built-in `crypto.verify` handles Ed25519; Python's standard library decodes the wire format.
- The first verified signature, fee payer and canonical message binding must match the declared `transaction-intent-1` contract.
- V0 messages with address table lookups are explicitly rejected. Independent lookup resolution is not implemented. Newer message versions, wrapped SOL and Token-2022 are unsupported. Many aggregator transactions therefore remain outside this lab's supported scope.
- Received finalized evidence is checked by the prior intent reconciler, including integer input/output amounts, fees, supported account creation/closure and native wallet changes. The complete signature vector must match the registered verified transaction.

These signatures authenticate the message, **not** RPC balances, finality, the chosen network, registration time, router semantics, quoted prices or profitability. The network remains caller-labelled; no genesis identity or blockhash validity is checked. A valid signature does not establish that the wallet owner intended the declared economic policy. The journal does not replace pre-signing validation, simulation, approval, spending limits or independent exit controls.

## Persistence and duplicate behavior

The journal directory must already exist, be owned by the invoking user and have mode `0700`. Its database is mode `0600`; symlinks, hard links, foreign application IDs and unsupported schema versions are refused. SQLite uses `synchronous=FULL`, rollback journaling, immediate transactions and a five-second lock timeout. Initialization fsyncs the parent directory. Process-death recovery is tested; power-loss guarantees still depend on the filesystem and storage hardware.

`register` atomically records the logical intent ID, signed identity hashes, verified signature vector, intent contract and local registration time. It does not retain the supplied signed wire bytes. Retrying the identical registration returns the existing state. Changing its contract under the same ID, or reusing the same signature under another ID or network label, is rejected. No state or daily counter is reset.

`boundary` commits `submission-unknown` **before** a future external sender would be called. This release includes no sender. The boundary can be crossed only once. A crash just afterward cannot tell us whether the transaction was sent; recovery preserves that uncertainty. A crash before commit rolls the boundary back. External callers must obey this ordering; this module cannot prove whether a transaction was broadcast elsewhere or prevent someone from bypassing the journal.

`observe` consumes a supplied `intent-evidence-bundle-1` for the registered contract. Outcomes are:

| State | Meaning |
| --- | --- |
| `prepared` | Verified identity and declared contract recorded locally |
| `submission-unknown` | Boundary recorded; execution is unresolved, including null/not-found evidence |
| `reconciled` | Supplied finalized balances match the registered signed identity and supported contract |
| `failed-fee-only` | Supplied finalized failure changed only the allowed fee |
| `quarantined` | Conflicting or unsupported receipt; automatic recovery is disabled |

An identical receipt retry is idempotent. Updated capture timestamps/RPC context slots do not conflict with the same finalized economic outcome. Conflicting finalized balances, fee/rent results, slot or failure result are quarantined. Unknown evidence cannot erase a prior final result. Quarantine is sticky; no reset/release command exists. All outputs keep `executionApproved=false`, `resubmitAllowed=false`, `networkRequests=0`, and `productionLedgerUpdated=false`.

The local journal is not an authenticated or tamper-proof audit log. Trusted owner access, local clock and original file continuity are assumed. Duplicate protection applies to logical IDs and signed identities inside this journal; wallet-wide risk limits, distributed coordination, wallet ownership proof and a production sender are future work. There is no journal pruning: 10,000 events or a 64 MiB file cap stops further work explicitly. This journal is not included in the scanner/quote backup jobs.

## Commands

Only the first command is needed for this release's host validation. It reads public fixtures, creates temporary private journals, exercises eleven cases, removes the journals and writes a private report:

```bash
cd ~/apps/solana-early-alpha-radar
python3 -E -s ~/apps/solana-radar-dev/intent-journal/intent_journal_cli.py \
  --output "$PWD/radar-signed-intent-check-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

Optional developer-only supplied-evidence interface, after deliberately creating a separate private directory:

```text
--action register --journal /private/path/intents.sqlite --input registration.json.gz --output report.json.gz
--action boundary --journal /private/path/intents.sqlite --id logical-id --output report.json.gz
--action observe --journal /private/path/intents.sqlite --id logical-id --input evidence.json.gz --output report.json.gz
--action status --journal /private/path/intents.sqlite --id logical-id --output report.json.gz
```

Each output filename must be new. Registration input has exactly `format: signed-intent-registration-1`, `logicalIntentId`, `intent` and `signedTransactionBase64`. Evidence uses the prior intent lab's format. Inputs are capped at 4 MiB after decompression; duplicate JSON keys/nonfinite numbers fail. Do not supply private keys or seed phrases. A report publication error can occur **after** a journal mutation commits; inspect `status` before retrying a mutation. Status/boundary/observe never create an absent journal. There is no installer or daemon.

## Fixtures and verification

`public-fixtures.json` contains six **synthetic** cases: existing, create, close, failed, v0 without lookups, and multiple required signatures. They use ephemeral generated Ed25519 keypairs; private keys were never exported or persisted. A separate JavaScript serializer produced their signed bytes, which the Python decoder independently checks. Balances, slot, router, blockhash and RPC finality are hypothetical; these transactions were never sent. No signing implementation or secret fixture keys are shipped. The public signed fixtures are not reusable accounts or funded wallets.

The self-check also exercises duplicate boundary rejection, idempotent registration, tampered-wire rejection, unknown/restart recovery and unexpected-debit quarantine. Unit tests additionally cover process termination before/after commit, concurrent connections, all required signatures, malformed wire counts/headers, unsupported formats, conflicting outcomes, permissions, clock regression and transaction rollback on caps. Recorded transaction and devnet tests remain outstanding.

Primary format/crypto references:
- https://solana.com/docs/core/transactions/transaction-structure
- https://solana.com/docs/core/transactions/versioned-transactions
- https://nodejs.org/docs/latest-v24.x/api/crypto.html#cryptoverifyalgorithm-data-key-signature-callback
