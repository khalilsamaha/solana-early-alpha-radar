#!/usr/bin/env bash
# One explicit upload/download of the accepted synthetic receipt-complete package.
set -euo pipefail
umask 077
if [ "$#" -ne 1 ] || [ "$1" != '--round-trip-b2' ]; then
  printf 'Usage: bash r1-package-b2-normal.sh --round-trip-b2\n' >&2
  exit 2
fi
app='/home/redeye/apps/solana-early-alpha-radar'
sha='04209213b38fdc29a37e0b830bc10cc09ed3f294'
tree='5451f9fa677e62600bd9dccbbc3088801e062c1d'
output="$app/radar-r1-package-b2-normal-9492acc0b036"
test -d "$app"
if [ -e "$output" ]; then
  printf 'Attempt directory already exists. Preserve it; do not retry or delete it:\n%s\n' "$output" >&2
  exit 1
fi
locate_report() {
  local pattern="$1" expected="$2" candidate actual found='' count=0
  for candidate in "$app"/$pattern; do
    test -f "$candidate/report.json" || continue
    actual="$(sha256sum "$candidate/report.json")"
    if [ "${actual%% *}" = "$expected" ]; then
      found="$candidate"; count=$((count + 1))
    fi
  done
  if [ "$count" -ne 1 ]; then
    printf 'Expected one accepted %s report; found %s. Stop.\n' "$pattern" "$count" >&2
    return 1
  fi
  printf '%s\n' "$found"
}
accepted="$(locate_report 'radar-r1-delivery-*' 'f6ca0fcaadd391a4579e8b34eabd6e9259745940c1290d1f6156202efd00179f')"
gate="$(locate_report 'radar-r1-remote-reconcile-*' '3f2e41dcfa37b759cd69304f7e1ca85a525dd4662da852414e4f63930ce1909e')"
review="$(mktemp -d "$HOME/apps/solana-radar-b2-package.XXXXXX")"
git init -q "$review/source"
git -C "$review/source" fetch --depth=1 https://github.com/khalilsamaha/solana-early-alpha-radar.git "$sha"
git -C "$review/source" checkout --detach "$sha"
test "$(git -C "$review/source" rev-parse HEAD)" = "$sha"
test "$(git -C "$review/source" rev-parse 'HEAD^{tree}')" = "$tree"
python3 -m venv "$review/venv"
"$review/venv/bin/python" -m pip --isolated --disable-pip-version-check install \
  --no-deps --only-binary=:all: --require-hashes -r "$review/source/r1-data/requirements-wire.txt"
printf 'This performs one B2 upload/download of 125546 synthetic bytes using the existing backup configuration. Existing storage/API charges may apply.\n'
# Authenticate only for the existing root-owned configuration; no permission changes.
sudo -v
mkdir -m 700 "$output"
printf 'Retain this attempt directory, including on failure:\n%s\n' "$output"
cd "$review/source"
timeout --signal=TERM --kill-after=20s 180s \
  "$review/venv/bin/python" -E -s -B -W error::ResourceWarning - "$accepted" "$gate" "$output" <<'PY'
import json
from pathlib import Path
import sys
import zipfile
sys.path.insert(0,str(Path.cwd()/'r1-remote-review'))
import reconcile as q
r=q.r
accepted,gate,out=map(Path,sys.argv[1:])
gate_raw=r.read_private(gate/'report.json',1024*1024)
if r.digest(gate_raw)!='3f2e41dcfa37b759cd69304f7e1ca85a525dd4662da852414e4f63930ce1909e':
    raise SystemExit('Kali gate identity mismatch; no transfer attempted.')
g=json.loads(gate_raw)
if g['source_sha256']!=q.pins() or g['tests']!={'run':35,'failures':0,'errors':0,'skipped':0}:
    raise SystemExit('Kali source/test gate mismatch; no transfer attempted.')
control=out/'control';control.mkdir(mode=0o700)
client=r.B2('normal');completion=None
try:
    completion=r.transfer(control,accepted/'normal-package.zip',accepted/'report.json','normal',client)
except BaseException:
    pass  # Retain partial evidence. Never retry or print raw process diagnostics.
inspection=q.inspect(control)
passed=completion is not None and inspection['recorded_completion_verified']
summary={'schema_version':1,'status':'synthetic-package-b2-passed-retention-pending' if passed else 'synthetic-package-b2-unresolved',
    'source_commit':'04209213b38fdc29a37e0b830bc10cc09ed3f294','source_sha256':q.pins(),
    'kali_gate_sha256':r.digest(gate_raw),'profile':'normal','package_sha256':r.PROFILES['normal'][1],
    'package_bytes':r.PROFILES['normal'][0],'synthetic_only':True,'calls':client.calls,'local_inspection':inspection,
    'roundtrip_reported_by_host':passed,'remote_observed_by_reviewer':False,
    'remote_object_may_exist':any(c['operation']=='upload' for c in client.calls),
    'retention_verified':False,'production_backup_coverage_verified':False,
    'automatic_retry_allowed':False,'live_launch_authorized':False,'full_gate_accepted':False}
r.d.o.write(out,'report.json',summary)
# Portable audit copy of the retained attempt, including partial failures.
# Never put this ZIP inside the control or alter its reconciled member set.
try:
    before=q.inventory(control)
    with zipfile.ZipFile(out/'attempt-evidence.zip','x',compression=zipfile.ZIP_STORED) as z:
        for name,entry in sorted(before.items()):
            if entry==['directory']:continue
            raw=r.read_private(control/name,1024*1024)
            if [len(raw),r.digest(raw)]!=entry:raise r.CaptureError('attempt-changed')
            info=zipfile.ZipInfo('control/'+name);info.external_attr=0o100600<<16
            z.writestr(info,raw)
    if q.inventory(control)!=before:raise r.CaptureError('attempt-changed')
except Exception:
    print('Attempt export incomplete. Preserve the entire directory for review.',file=sys.stderr)
print(summary['status'])
print('Upload report.json and attempt-evidence.zip; preserve all originals.')
raise SystemExit(0 if passed else 2)
PY
