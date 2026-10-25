# Explicit recovery of the refused cycle-2 entry

The October 25 host reports passed ten checks and returned `unsigned-reservation-verified`. The sealed preparation is `77c7cb1b2da3f1b01968c99dad750a2aba817c5f8dd6067faada758c4b3bf901`; the reviewed unsigned evidence fingerprint is `26bb26b8cd23a9d4c2d2d5d669e325b9657ce2eec63bc0738607c25099ea6514`. No signing attempt, signed transaction or submission boundary exists. The packet expired. Historical confirmed fees remain 10,000 lamports, with 20,000 reserved for cycle 2 and 1,000 atomic input units held.

This release allows one explicit replacement of that refused unsigned entry. It does not replace a signed transaction, retry an uncertain submission, reset a ledger or increase spending limits. The scanner, quote observer, backups and frozen study are unchanged. The study review remains October 27.

## Durable transition

Preparation requires both exact reviewed hashes, the original single reservation event, a signing-phase refusal, expiry of both policy and signing request, the exact six-file unsigned journal, and absence of any signing/submission marker. It uses the common wallet lock and the independent reservation validator. Root STOP blocks preparation.

1. Write `unsigned-replacement.json`, binding the approved evidence, original reservation and ledger head.
2. Rename the original directory to `refused-unsigned-entry-v1` and sync the parent. Every original file is preserved byte-for-byte.
3. Append a replacement authorization to the existing spending ledger. Keep the original leg and full budget held.
4. Write `unsigned-replacement-ready.json`. No private key or network is used during preparation.

Preparation is idempotent for the same approved evidence and can resume after interruption between these complete durable steps. Partial, corrupt, changed or ambiguous evidence fails closed; it is not silently repaired. Repeating preparation after a fresh entry does not authorize another attempt.

The explicit replacement entry then uses the existing sender with fresh deployment/account checks, current balance continuity, a new blockhash, fee evidence, signed simulation and pre-send validation. A single atomic ledger event transfers the still-held reservation to the fresh contract and retains the old leg in its history. The Node signer independently verifies the archived files, replacement seal, original ledger head, authorization and new reservation before key access. A repeated blockhash is refused. Root STOP continues to apply.

If fresh packet construction or preflight fails, the report still shows the held reservation. A failed replacement attempt cannot obtain another replacement through this release. Once signing starts, existing unknown-outcome, one-send, receipt-reconciliation and read-only recovery rules apply. No funds are released based only on expiry or missing RPC evidence.

## Kali commands

Use the pinned release commit from chat; no production rebuild or service restart is needed. The command-line entry point is `devnet-pool/cycle_replacement_cli.py`.

- Default `self-check`: twenty tests with disposable unfunded wallets and synthetic RPC, including process death and interrupted preparation. Allow roughly one to two minutes.
- `prepare`: requires `--allow-unsigned-plan-replacement`, `--expected-preparation` and `--expected-evidence`. It cannot send or sign.
- `entry`: requires `--allow-devnet-submit`; consumes the one prepared unsigned replacement.
- `status`: reads prepared/local entry state without the key or network.
- `recover`: observes the current cycle-2 entry with the existing read-only recovery implementation; it never resends.

All non-self-check actions require the explicit wallet, pool and dedicated directory. Permission flags are action-specific; status/recover refuse submission permission. Every command requires a new public output path.

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/devnet-pool/cycle_replacement_cli.py" \
  --action prepare --allow-unsigned-plan-replacement \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --expected-preparation 77c7cb1b2da3f1b01968c99dad750a2aba817c5f8dd6067faada758c4b3bf901 \
  --expected-evidence 26bb26b8cd23a9d4c2d2d5d669e325b9657ce2eec63bc0738607c25099ea6514 \
  --output "$PWD/radar-unsigned-preparation-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected preparation state: `unsigned-replacement-prepared`, with no signing or sending and the same 20,000-lamport reservation. A successful subsequent entry is `finalized-success`, with at most one application send request. Recovery must show zero sends. Review its public receipt before the separate reverse command. Do not delete or edit journals, repeat entry as a retry, or add/use funds in the dedicated wallet during this cycle.

## Scope and limits

This is a fixed controlled devnet pool. Same-user filesystem ownership, the shared lock and RPC evidence remain trust assumptions; someone with the private key can bypass this application. No mainnet trading or strategy profitability is established. The existing two-cycle gross allocation and cumulative fee cap are preserved. The next acceptance gate is the fresh entry receipt and independent recovery report, followed by the exact-quantity reverse and cumulative accounting review.
