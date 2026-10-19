# Program deployment capture — 19 October 2026

The supplied pool-state reports passed exact local replay: all fifteen synthetic cases and the actual seven-request devnet observation. The real pool snapshot at slot 512847269 validated its supported account relationships. Both test token mint authorities remain present; structural consistency is not a token-quality endorsement.

This release adds `swap-program/`, a standalone full ProgramData capture and change comparator. It records the payload hash including allocation padding, deployment slot and upgrade authority; the Program and ProgramData pointers must agree within one finalized account batch. An optional earlier capture is recomputed from its raw bytes for comparison. Code, authority and redeployment changes are kept distinct from normal observation/balance changes. No summary field can grant signing permission.

The default CLI runs fourteen deterministic cases without a network. `--capture-devnet` makes at most five read requests; it never signs or sends. Actual ProgramData capture is a Kali verification gate. No scanner rebuild, service restart, wallet funding, private key input or cloud download is needed.

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
radar_stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
python3 -E -s "$HOME/apps/solana-radar-dev/swap-program/program_cli.py" \
  --output "$PWD/radar-program-check-$radar_stamp.json.gz"
python3 -E -s "$HOME/apps/solana-radar-dev/swap-program/program_cli.py" \
  --capture-devnet --output "$PWD/radar-program-capture-$radar_stamp.json.gz"
SH
```

Update the development checkout to the published release commit first. Upload both output files, including an unavailable or unsupported capture if one occurs. Do not resample to find a pass. Details, manual comparison commands, limits and primary sources are in [the module README](../swap-program/README.md).

This is deployment observation and drift detection, not source-to-binary equivalence. Next: review actual deployment evidence, define the independently reviewed program baseline, and then connect restricted simulation/signing to the existing durable accounting path. No real-money or profitability gate has been passed by these engineering reports.
