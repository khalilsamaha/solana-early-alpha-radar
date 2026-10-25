# Cycle-2 preparation hash correction

The October 25 local diagnostic confirmed that Python matched the sealed cycle preparation while the Node signer did not. The 17,296-byte preparation contained three integers beyond JavaScript's safe integer range and sixteen floating-point values. Plan and preflight hashes agreed in both languages; the prior-source hash also agreed. No signing attempt, signed transaction or submission boundary was present. The reserved round-trip fee remains 20,000 devnet lamports, with historical confirmed fees of 10,000.

The Node signer previously parsed the complete Python-written preparation and serialized it again before hashing. JavaScript can round large RPC integers and change numeric spellings such as `1.0` to `1`, changing the digest even though the original file is intact. It now hashes the original, bounded preparation bytes and requires that hash to match both the seal and the plan's cycle binding. Python continues to replay and validate the preparation, its canonical hash, funding and prior receipts. The Node signer still independently validates the compact source, policy, historical spending, current reservation and fixed instruction scope. No historical evidence is rewritten or normalized.

The new `devnet-pool/cycle_reservation_cli.py` has only two actions: offline self-check and read-only inspection of the existing refused, unsigned entry. It uses the same shared wallet lock and the same independent Node reservation validator as signing. It does not import the signing executable, access the private key, make RPC requests, modify the spending ledger or grant execution permission. It requires the exact unsigned-failure file set and refuses if any signing attempt, signed transaction, submission boundary or unexpected file exists.

## Host procedure

Use the exact release commit supplied in chat. No Docker rebuild, scanner restart, observer reinstall or study change is required.

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/devnet-pool/cycle_reservation_cli.py" \
  --output "$PWD/radar-cycle-hash-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"

python3 -E -s "$HOME/apps/solana-radar-dev/devnet-pool/cycle_reservation_cli.py" \
  --action inspect \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-cycle-reservation-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: ten offline checks, then `unsigned-reservation-verified`, `preparationHashBasis: sealed-file-bytes-v1`, no key/network/signing activity, unchanged reservation, and `packetExpired: true` for the October 24 entry. Upload only these public reports. The audit is a check of local historical evidence, not a refresh of wallet balances or execution approval.

## Recovery boundary

This release corrects the validator but deliberately does not reset the failed entry, release its reservation, rename journals or resume execution. The saved packet has expired. Existing `entry` still returns the saved state without another send. An explicit unsigned-plan replacement needs a separate durable transition that preserves the rejected attempt and its reservation history, proves the absence of a signing attempt, and obtains fresh balance/deployment/blockhash evidence before any new signing. A signed or uncertain attempt must never qualify through this path.

The host inspection is the next acceptance gate for that recovery work. The frozen research study remains unchanged, with review on October 27. Devnet execution evidence remains separate from strategy profitability or mainnet approval.

## Regression coverage

Tests exercise preparation with u64-sized RPC fields, integral floats and Unicode; a complete synthetic entry/reverse through the corrected signer; changed bytes that JavaScript would round to the same Number; refusal of changed seals, requests and ledgers; marker-based exclusions; standalone CLI operation; expired-plan non-retry; and byte-for-byte preservation of local files without a private key.
