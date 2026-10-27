# Preflight failure diagnostics — 27 October 2026

The supplied unsigned-simulation self-check exactly replayed all 13 cases.
The actual 18:19 UTC attempt was `unavailable` at `pool-quote` after four public
reads. It made no simulation request, signatures, sends or source-journal changes.
Its report exposed only `initial-preflight-rejected` / `capture-incomplete`.
That is not enough to distinguish a deployment change from transport or decoding
failure. It is not a successful simulation checkpoint.

This correction adds diagnostic summaries to both fresh observation modes and
the existing standalone preflight CLI. It retains:

- An allowlisted collector stop reason, per-request/evidence states and numeric
  HTTP status when available.
- A bounded comparison of independently decoded public deployment fields against
  the existing internal pin, if the partial account batch is usable. It records
  changed field names, identity hashes and observed decoded public fields.
- Explicit unavailable status when the account batch cannot be decoded or bound.

No raw provider error text, arbitrary keys, logs or response bytes are copied into
the summary. The preflight CLI already includes the sanitized raw public capture
needed for later replay; it makes no request beyond its existing collector.
Diagnostics are not an acceptance path. A matching partial program identity does
not complete the missing preflight checks. No pin, deadline, cap, signer, sender,
runtime service, observer quota or frozen study is changed.

## Host checkpoint

Fetch the exact revision supplied in chat. Run this **read-only** capture first;
do not repeat simulation or execution until the cause is reviewed. No private
wallet directory, sudo, Docker rebuild or service restart is required.

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/swap-preflight/preflight_cli.py" \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-preflight-diagnostic-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

Upload the generated report even when it says `unavailable`. If a deployment
change is confirmed, review the new public evidence before considering a new pin;
never copy the current hash into the baseline merely to obtain a pass. If it is
a transport/schema issue, fix that specific cause while keeping the pin.

This is a focused correction in the current development batch. Tests cover a
four-read deployment stop, a four-read network failure, HTTP status, hostile
diagnostic text, malformed and oversized accounts, unchanged acceptance and
unchanged baseline. No extra public calls are used by tests or diagnostics.
The October 28 17:30 Europe/Amsterdam frozen review remains unchanged.
