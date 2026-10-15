#!/bin/bash
set -euo pipefail
umask 077
output="$PWD/radar-auto-quotes-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
tmp="$(mktemp "$PWD/.radar-quotes-export-XXXXXX")"
trap 'rm -f "$tmp"' EXIT
sudo python3 -E -s /usr/local/lib/solana-radar-quotes/0.8.0/manage.py export "$@" > "$tmp"
python3 - "$tmp" <<'PY'
import gzip,json,sys
with gzip.open(sys.argv[1],'rt') as f:r=json.load(f)
assert r['format']=='quote-observer-report-0.2.0'
print('Signals:',len(r['signals']),'; probes:',len(r['probes']))
print('Probe states:',r['probeCounts'])
for key,g in r['exitEvidence']['groups'].items():
    h=g['horizons'].get('120000',{});mean=h.get('meanQuotedChangePct')
    print(f"{key}: 120s quoted={h.get('quotedReturns',0)}/{g['admitted']}; mean={mean:.2f}%" if mean is not None else f"{key}: no final quoted returns")
    print('  Exit evidence:',dict(h.get('states',{})))
print('Quoted changes are not fills or net profit. Explicit signal/buy/exit clocks are in exitEvidence.')
PY
mv "$tmp" "$output"
trap - EXIT
printf 'Upload this report: %s\n' "$output"
