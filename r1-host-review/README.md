# R1 read-only host identity review

This follows Kali acceptance of the shared owner/Node integration at `df6cbfa4`.
It answers whether the currently observed container process identity aligns with
the same-UID private socket design. It does not authorize or perform a rollout.

The runner executes synthetic regression tests, then makes at most two fixed
`docker inspect --type container --format ...` calls for
`solana-early-alpha-radar-radar-1`. It uses `/usr/bin/docker`, the local root-owned
`/run/docker.sock`, an empty temporary Docker configuration and a minimal
environment. There is no context selection, remote endpoint, sudo escalation,
container exec, restart, stop, build, pull, image change or new container.

Only selected identity, state and hardening fields enter Python/report output.
The format does not select environment, command arguments, mounts, labels or logs.
Docker itself retrieves inspection data internally; this is not a claim that
the daemon/API response contains no sensitive configuration. All CLI stderr is
discarded. Output is capped at 16 KiB and each command at four seconds, with
forced cleanup on failure. No error text or arbitrary stdout is copied into
the report, and no failed operation is automatically retried.

The review reads bounded numeric UID/GID, process-start and immediate-child
metadata from `/proc`, plus user-namespace identifiers. Both selected PIDs must
show the exact inspected container ID in their cgroup membership; otherwise a
PID-namespace mismatch could identify an unrelated process. Raw cgroup paths
are not exported. If Docker reports an
init wrapper, exactly one direct child must exist; otherwise the result is
unavailable rather than guessing which process is the scanner. The observation
does not authenticate that process's executable. A second inspection and process
snapshot detect container replacement, restart, PID reuse or child replacement.
This is a bounded observation, not an atomic snapshot or a guarantee about later
credentials/processes.

UID or namespace differences, root invocation, unconfirmed health and hardening
differences are explicit findings. Even matching numeric identities do not prove
Docker bind-mount permissions or an actual production IPC handshake. No application
database, provider key, wallet, backup configuration or raw provider stream is read
by this Python program. Temporary test/CLI-config files and the requested report
are the only filesystem writes.

From the supplied pinned independent checkout, run as the normal Kali user:

```sh
timeout --signal=TERM --kill-after=5s 40s \
  python3 -E -s -B -W error::ResourceWarning r1-host-review/check.py \
  --output /absolute/new/host-identity.json --observe-local-container
```

No venv or dependency installation is required. Expected completed observation:
`host-identity-observed-rollout-blocked`. If Docker/proc access is unavailable or
identity changes during observation, the runner writes
`host-identity-unavailable-rollout-blocked` with a fixed error code. Upload that
report once too; do not add sudo, change permissions or repeat it automatically.
Exit zero means the report was written, not that rollout is permitted. Existing
reports and symlinks are never overwritten.

This is the next concrete dependency for the host-broker/container integration.
After review, prepare the matching IPC ownership/mount and startup/rollback plan,
complete live credential and supervision controls, and register measurement and
exposure terms before activation. The existing five-working-day effort cap is
unchanged. Full-gate Kali acceptance still precedes PR/CI consolidation and the
owner's merge decision. No funding, live feed activation or ML fitting is enabled.

Reference interfaces checked: [Docker inspect](https://docs.docker.com/reference/cli/docker/inspect/),
[Docker CLI configuration](https://docs.docker.com/reference/cli/docker/), and
[Linux process status](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html).
