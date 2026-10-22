# Controlled receipt position ledger

This release connects the completed controlled devnet entry/reverse to durable historical position accounting. It does not modify scanner rules, observer quotas, the protocol, the live dashboard or backup jobs. No Docker rebuild is needed.

## Evidence boundary

`position-book/controlled_cli.py --action sync` shares the dedicated execution lock and replays the local setup, signed entry and reverse journals using the existing strict validators. It does not instantiate the key-reading session, access private keys, query RPC, sign or send. It accepts no uploaded summary as an accounting input.

The new `controlled.positions.sqlite` stays in the dedicated private devnet directory. SQLite commits one bounded snapshot event atomically, with owned 0600 storage, a 64-event cap, 16 KiB per snapshot and hash-linked event checks. Repeating a sync after restart does not duplicate inventory or fees. These hashes detect accidental inconsistency; they do not defend against a malicious same-user rewrite of all evidence.

Open acquisitions exclude the holder's pre-existing token balance. Unknown exit outcomes retain the last reconciled quantity and confirmed fees, without claiming current spendable balance. A finalized failed exit leaves inventory open and records its actual fee. Conflicting, missing or regressed source evidence quarantines an existing position; quarantine remains sticky. Preserve journals for diagnosis rather than deleting them to make a check pass.

`historicalImport=true`, `pretradeBudgetEnforced=false` and `liveUseAllowed=false` are always reported. The generic offline position book is not backdated, and the acquisition's old submission boundary is not portrayed as a prospective reservation. Next work is explicit integration of those controls before future controlled submissions.

## Host commands

Use the pinned release checkout supplied in chat. Run from the existing live project directory. The default self-check uses disposable, unfunded wallets and synthetic RPC fixtures:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
radar_stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
python3 -E -s "$HOME/apps/solana-radar-dev/position-book/controlled_cli.py" \
  --output "$PWD/radar-position-check-$radar_stamp.json.gz"
python3 -E -s "$HOME/apps/solana-radar-dev/position-book/controlled_cli.py" \
  --action sync \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-position-import-$radar_stamp.json.gz"
SH
```

For the supplied receipts, expect `closed`, residual `0`, original-token net `-3`, confirmed fees `10000`, and one import event. Repeating sync should show `ledgerChanged=false` and no additional event. A quarantine exits with status 2 and still publishes its public report; other validation errors stop without a success report.

Upload the two public `.json.gz` reports. The small accounting database and private signed journals are not upload reports and are not automatically covered by scanner/quote backup jobs.

## Refresh strategy readiness from existing evidence

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
radar_dev="$HOME/apps/solana-radar-dev"
radar_registration="$PWD/radar-forward-protocol-registration.json.gz"
radar_review="$PWD/radar-forward-check-$(date -u +%Y%m%dT%H%M%SZ)-$$"
test -f "$radar_registration"
mkdir -m 700 "$radar_review"
sudo python3 -E -s "$radar_dev/research-dataset/history.py" \
  --hours 72 --output-dir "$radar_review/capture"
python3 -E -s "$radar_dev/forward-study/readiness_details.py" \
  --history-dir "$radar_review/capture" \
  --registration "$radar_registration" \
  --output "$radar_review/readiness-details.json.gz"
printf '\nUpload: %s/readiness-details.json.gz\n' "$radar_review"
printf 'Keep the capture directory: %s/capture\n' "$radar_review"
SH
```

This reads the local quote ledger, preserves the registered comparison and trains no model. It performs no cloud transfer. The development checkout changes; the running scanner/observer and production Compose configuration do not.
