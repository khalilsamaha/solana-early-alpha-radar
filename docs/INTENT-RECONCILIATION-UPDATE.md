# Transaction-intent engineering release — 17 October 2026

## Confirmed host state

The user's 16:15 UTC inventory verified release `0637e808492affd8b8f9189cad58353ea3ca2ba8`: 52/52 scanner host files, 51/51 container files and 27/27 observer files match. The scanner is healthy with zero restarts since 16 October at 03:34 UTC; observer 0.9.0 is running. The offline chain self-check and the detailed readiness replay match the local results exactly. No deployment correction was needed.

The readiness report reused the capture ending 17 October at 09:44 UTC. It is not evidence from the later report-generation time. It still contains 166 compatible watches across two days, negative mean returned 30-second quoted changes in all three cohorts, and unmet fitting guards. No model or trading rule was promoted.

## This release

Adds an isolated offline intent-reconciliation lab. It checks a declared prior transaction message, public wallet, input/output token accounts and mint identities, integer input debit/minimum output, fee/rent limits and native-wallet changes. It supports a narrow standard SPL account creation/closure evidence path and explicit finalized-failure fee accounting. Unknown/missing/provisional evidence cannot authorize resubmission.

The output distinguishes balance consistency, fee-only finalized failure, mismatch, unknown, unsupported and malformed input. Every outcome remains non-authorizing and no ledger is changed. The lab does not sign, submit, simulate on-chain or call a provider. It has no runtime service and needs no scanner rebuild or observer restart.

Supported lifecycle subset: standard SPL Token Program, non-native tokens, wallet fee payer, existing accounts, System CreateAccount plus InitializeAccount3 for a destination, and CloseAccount for a fully debited source. Wrapped SOL, Token-2022, other initialization paths and unsupported account operations remain explicit limitations. This is foundational execution engineering, not universal meme-token execution support.

The prepared-message binding is a canonical parsed-message hash, not a cryptographic signature check. Intent registration and network labels are asserted by the input. Independent signature/chain verification, durable intent registration, router instruction validation and recorded/devnet validation remain next work. See [complete contract and limitations](../intent-lab/README.md).

## Run after checking out the pinned release

```bash
cd ~/apps/solana-early-alpha-radar
python3 -E -s ~/apps/solana-radar-dev/intent-lab/intent_cli.py \
  --output "$PWD/radar-intent-self-check-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

Expected: `six offline scenarios passed`, followed by a report path. Upload that report. This is a synthetic host check; no wallet or public transaction identifier is required.

Continue the existing scanner and quote collection. Reassess the fixed ML guards from a new capture when additional data is available; do not reuse this morning's capture as evidence of progress. No new collection window, budget, protocol or Backblaze setting is introduced by this release.

## Validation

664 automated tests passed locally: 642 source/regression checks and 22 offline ML/model checks, including 30 new intent tests. The six-scenario CLI report also passed. Source comparison confirms scanner, quote observer, research collectors/models/protocol, deployment scripts and backup tools are unchanged. No live or devnet transaction was submitted or validated by these tests.
