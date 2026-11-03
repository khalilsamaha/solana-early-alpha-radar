# Preserved exit inspection — 3 November 2026

The controlled devnet entry was acknowledged and its receipt reconciled. The
06:31:37 UTC status report verifies `exit-prepared`, 1,000 source atomic units
spent, 998 acquired units held, a 5,000-lamport paid fee, and 25,000 lamports still
reserved. The entry and exit are not a completed round trip. The exit report
recorded zero signer invocations and zero send requests. Its generic failure code
does not prove which pre-sign validation failed, although the report was completed
after the saved deadline.

This increment adds `position-book/exit_preparation_audit_cli.py`. Default action
`check` runs disposable offline cases. Explicit action `inspect` replays the
source and admission lifecycle under existing source and SQLite read locks, then
reports the original preparation identity, deadline, expiry, signing record and
fixed backend marker presence. Markers include dangling symlinks; their contents
are not read. Corrupt or conflicting ledger evidence suppresses partial accounting.
Marker presence without a signing record is explicitly classified for inspection.

Every SQLite connection is read-only. Inspection makes no RPC requests, reads no
private key, creates no signature, sends no transaction and changes no source
journal, deadline, STOP state or reservation. The public output is a new private
report file outside the source and both fixed handoff directories. Repeated output
paths are refused. No replacement or retry authorization is produced, even when
an unsigned preparation is expired and neither marker exists.

Fresh exit diagnostics now identify the signing-validation stage before adapter
invocation. Three existing bounded signing failure codes are preserved rather
than hidden behind a generic error. Unknown exception text remains sanitized.
The signing and sending order, deadlines and execution decisions are unchanged.

## Validation

All 24 targeted local tests passed: six inspection/CLI tests (including eleven
portable cases), twelve fresh-exit tests including the actual disposable-key
backend, and six lifecycle regression tests. Two CI partition checks and source
hygiene/package manifests also passed. No live RPC was used. Host inspection is
still pending; these local results do not establish the user's marker state.

## Host inspection

From the production project directory, with the pinned development checkout:

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/position-book/exit_preparation_audit_cli.py" \
  --output "$PWD/radar-exit-preparation-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"

python3 -E -s "$HOME/apps/solana-radar-dev/position-book/exit_preparation_audit_cli.py" \
  --action inspect \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-exit-preparation-inspect-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Upload the two public reports. No Docker rebuild or service restart is required.
Do not retry `exit`, delete a preparation, edit a deadline or release reservations.

## Next gate

If the replay confirms expired unsigned evidence with no signer markers, the next
implementation is an explicit, history-preserving replacement contract. It must
refuse every signing/transport uncertainty, preserve the original preparation,
revalidate settled entry ownership and current state, and bind freshly collected
evidence to its own original deadline. This inspection does not implement that
contract. Signed or ambiguous evidence continues through existing recovery only.

Production discovery, scoring, notifications, the quote observer and the frozen
study are unchanged. Controlled devnet recovery and economic qualification remain
separate unfinished gates; no real-money pilot is approved by these results.

## Subsequent host result

The 06:44:29 UTC inspection and all eleven portable cases passed. The saved
preparation is expired and unsigned, with both signer markers absent and scoped
holds intact. The next [internal replacement contract](UNSIGNED-EXIT-REPLACEMENT.md)
preserves this history; operational replacement/signing is not yet enabled.
