#!/usr/bin/env bash
# Read-only local recovery evidence. Does not start, stop, reset or alter anything.
set -u
umask 077
cd "$HOME/apps/solana-early-alpha-radar" || exit 1
sudo -v || exit 1
radar_recovery_report="$(mktemp "$PWD/radar-reboot-check-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX.txt")" || exit 1
check() {
  printf '\nCommand: '; printf '%q ' "$@"; printf '\n'
  "$@"
  printf 'Exit status: %s\n' "$?"
}
{
  printf 'Radar recovery evidence. Read-only; no external network requests.\n'
  printf 'User reported approximately three hours offline due to reboot. Exact interval is not established by this report.\n'
  check date -Is
  check uptime -s
  check timedatectl show -p Timezone -p NTPSynchronized
  check sudo timeout 10s journalctl --list-boots --no-pager -n 3
  check sudo timeout 15s docker compose ps
  radar_container="$(sudo timeout 15s docker compose ps -q radar)"
  if [[ "$radar_container" =~ ^[a-f0-9]{12,64}$ ]]; then
    check sudo timeout 10s docker inspect --format 'Created={{.Created}} StartedAt={{.State.StartedAt}} FinishedAt={{.State.FinishedAt}} RestartCount={{.RestartCount}} OOMKilled={{.State.OOMKilled}} Status={{.State.Status}} Health={{.State.Health.Status}}' "$radar_container"
  else
    printf 'No single running radar container could be identified.\n'
  fi
  check curl --max-time 10 --silent --show-error --write-out '\nHTTP %{http_code}\n' http://127.0.0.1:8787/readyz
  for radar_unit in docker.service containerd.service cron.service solana-radar-quotes.service solana-radar-research.timer solana-radar-backup.timer solana-radar-quotes-backup.timer; do
    check systemctl show "$radar_unit" --no-pager -p Id -p LoadState -p UnitFileState -p ActiveState -p SubState -p Result -p ExecMainStatus -p ActiveEnterTimestamp -p ExecMainStartTimestamp -p NRestarts -p LastTriggerUSec -p NextElapseUSecRealtime
  done
  check sudo timeout 20s python3 -E -s /usr/local/lib/solana-radar-quotes/0.9.0/manage.py status
  printf '\nInterpretation: a running process is not evidence of continuous coverage. Prior boot last-log time is not necessarily shutdown time. Quote interruptions and missing windows remain unavailable, never zero-return fills.\n'
} > "$radar_recovery_report" 2>&1
printf 'Upload: %s\n' "$radar_recovery_report"
