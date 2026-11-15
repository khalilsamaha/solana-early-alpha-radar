# Read-only production-context intake

Native isolated supervision is accepted; its fixture identities cannot identify
or authorize the current production scanner. This collector supplies the next
bounded factual input for designing the production adapter. It has no mutation,
activation, provider, credential or container-exec API.

The target is fixed to `solana-early-alpha-radar-radar-1`, using only the trusted
local Docker binary/socket and a new empty client configuration. The collector
makes one pass: two allowlisted metadata snapshots and two running-container
censuses around the existing host-identity observer's two identity snapshots.
There are six bounded read-only Docker requests, plus that observer's bounded
/proc UID/GID, namespace, process-generation and cgroup reads. There is no retry,
continuous monitoring or timing rehearsal. Changed/missing/inaccessible input
produces an unavailable report and leaves rollout blocked.

The metadata projection includes exact container/image identity, selected state,
Compose project/service, user and working directory, restart/resource settings,
network mode and at most sixteen mount descriptors. The census covers only running
containers carrying this project's Compose label. Environment, argv/command,
mounted files, executables and credentials are not read. No production filesystem
capacity, RPC, balance or provider observation is attempted. Review-directory and
private evidence files are the only writes; nothing is written to production.

The metadata digest binds only that projection. It is not a full configuration
hash. One project container does not prove a single global upstream owner: host
processes, other labels, other namespaces and external machines are outside this
census. Both `sole_owner_verified` and `full_configuration_verified` remain false,
as do production IPC, activation and automatic-resume authority. This package
cannot release holds or supply missing pilot approval.

Run `bash scripts/r1-production-context-kali.sh` from a fresh, clean, pinned checkout
named `source`. Return `results/production-context.zip` whether observation succeeds
or is unavailable. Do not rerun or change permissions in response to a failure.
The bundle contains only the report and test results. A valid unavailable report
is evidence of missing access, not evidence about the production scanner's state.

Local validation is `python3 -B -W error::ResourceWarning
r1-production-review/check_intake.py --offline --output-directory <fresh-directory>`.
Offline mode runs metadata/report tests but explicitly does not attempt a host
observation. The source-pinned existing host identity observer is reused unchanged.
