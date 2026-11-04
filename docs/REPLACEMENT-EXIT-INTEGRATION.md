# Connect one unsigned replacement to signing and one-send transport

The November 3 host report at 06:59:48 UTC passed all seventeen unsigned replacement
checks. The actual controlled devnet position remains open: the original expired
preparation is preserved, with no observed exit signing or submission. This
increment does not operate on that position.

## Changes

An internal `fresh_exit.replace_sign_submit` wrapper requires three exact opt-ins:
replacement, private-key signing and devnet submission. The caller identifies the
original preparation hash. Eligibility is checked before collection and again by
the existing replacement transaction. A returned preparation must preserve that
hash, report exactly one replacement, and be created in this attempt.

The independent Node signer now reads the bounded replacement row, validates the
original at its persistence time, checks the relationship and validates the current
record at signing time. It rejects rehashed lineage, ownership, fee, protection,
blockhash and timing conflicts before reading a key.

The existing signing and transport pipeline consumes that precise replacement
hash and its original collection deadline. The ten-second collection freshness
and thirty-second overall monotonic budget are unchanged. The independent signer,
STOP checks, exact message/quantity/fee checks and durable one-send boundary remain
in force. The normal fresh-exit wrapper rejects the internal replacement argument,
so its original vacancy contract cannot accidentally enable replacement.

A failed persistence still reports the actual collection request count. After a
replacement commits, another call is refused before collection, including when
signing or submission was interrupted. Lost replies preserve uncertainty and held
inventory; recovery observes the recorded signature without signing or resending.
No automatic retry, fee release, allocation transfer or subsequent cycle is added.

## Validation and interpretation

The portable exercise covers seven failure boundaries and exact opt-ins, then uses
a disposable full historical source, the actual isolated Node signer and synthetic
RPC to connect replacement to a single lost-response send. It verifies both old
records are unchanged, the signer references the replacement, repeated execution
is refused, and keyless recovery under STOP observes the existing signature.

The original preparation expires by real wall time in this test. The replacement
uses a distinct blockhash. Timings include local validation, persistence and actual
disposable-key signing, but exclude real RPC and finality latency. A local or host
pass therefore does not establish adequate live timing headroom or profitability.
The CLI accepts only an output path and cannot target an existing wallet or ledger.

Local validation passed eighteen targeted tests across the connected replacement,
existing fresh-exit pipeline and independent restricted signer, plus two partition
checks and source/package hygiene. The final portable run passed twelve checks
(including ten independent contract cases) and took 3,121.656 ms for its measured
replacement/sign/send stage. This is one synthetic sample, not a live latency
guarantee. Kali acceptance passed on November 4 at 04:23:09 UTC: all twelve checks and ten
independent signer cases passed. The measured replacement/sign/send stage was
6,546.413 ms, with one synthetic send and keyless recovery without resubmission.
This is still synthetic timing; live freshness must be enforced during the action.

## Kali check

After fetching the pinned development commit, run from the production project
folder:

```bash
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/replacement_exit_cli.py" \
  --output "$PWD/radar-replacement-exit-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-integration-passed`, twelve portable checks, including ten
independent signer-contract cases. Upload the public
report. No Docker rebuild, service restart, wallet funding or repeated `exit`
command is required. The production scanner, quote observer and availability
study continue unchanged.

## Next gates

Review the host result and local timing, consolidate this three-increment batch
with CI, then prepare the tightly scoped controlled devnet replacement command if
the evidence supports it. Actual finalized exit receipt reconciliation and scoped
closure must still complete. Mainnet execution, economic qualification and any
real-money pilot remain separate decisions.
