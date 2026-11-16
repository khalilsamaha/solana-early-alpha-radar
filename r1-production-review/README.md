# Read-only production-context intake

**Current:** the November 16 10:01:36 CET readiness report at `8eb329e1` completed
every stage, with fourteen matching source fingerprints. That observation is
accepted; no unchanged rerun is requested. It identifies nineteen running
containers but gives no workload attribution for the eighteen other containers.

`ownership.py` and `scripts/r1-production-ownership-kali.sh` collect that specific
missing input. They anchor to the accepted report digest, locate only prior
private readiness artifacts, and read fixed names/images/Compose labels/network
and running/PID metadata for exact currently enumerated IDs in groups of eight.
They read no command/environment values and invoke no container exec or mutation.
Two censuses surround the inventory; changed mid-pass membership or failed input
produces unavailable evidence, not a retry. At most 64 IDs, eight inspect calls
and two census calls are allowed. Each Docker call retains the four-second,
16 KiB bound and child cleanup. A nineteen-container pass uses five calls.

The output is `production-ownership.zip`. Success still says review-pending:
metadata alone cannot classify a workload's connections or prove global ownership.
Host processes, other daemons/machines and provider usage are outside scope.
Neither this inventory nor the prior readiness observation authorizes rollout.
See the [current scope and evidence record](../docs/R1-ENGINEERING-TO-PILOT-20261116.md).

**Current R1.A optional-field repair:** the supplied November 16 09:47:20 CET
report identified `docker-template-field-unavailable-StopSignal` at
`configuration-before`; later observations were not-run. The template now indexes
all allowlisted optional Config/HostConfig fields and guards missing labels;
omitted leaves project null without exporting whole configuration objects.
Missing stop settings remain unconfirmed. Forty-seven local tests pass; actual
Docker template execution still requires Kali. The new pinned read-only check is
scoped in the [engineering record](../docs/R1-ENGINEERING-TO-PILOT-20261116.md).

**Previous R1.A diagnostic repair:** the November 16 06:34:22 CET readiness
attempt was unavailable and discarded its failure stage. The repaired readiness
collector emits schema version 2 with a fixed `stages` ledger and safe `failure`
stage/code/source-line data. It retains no raw exception or Docker diagnostic.
Later stages are not-run; a stage marked completed means its function returned,
not that optional storage or configuration findings passed. An unavailable result
has no coherent `observation`, returns exit 1 and still produces the private ZIP.
No automatic retry is performed. The accepted original context check below does
not need another independent run. See the current disposition and exact changed
host-check scope in the [engineering record](../docs/R1-ENGINEERING-TO-PILOT-20261116.md).

The readiness-specific command runner reads at most 16 KiB stdout and 4 KiB stderr
per request, within four seconds plus bounded child cleanup. Only fixed categories
such as template-unavailable or permission-denied leave stderr handling; a missing
template field may be identified only from the fixed source-owned field allowlist.
These categories do not prove a root cause. Reports do not export stderr, stack locals,
raw commands, environment values or credentials. The successful configuration
projection is unchanged. The whole readiness path has at most eleven Docker
requests; source/proc/filesystem metadata observations retain their existing
read-only scope. The per-command deadline is not a whole-program filesystem
deadline. No additional production request is added for diagnosis.

Local changed-boundary validation:
`python3 -B -W error::ResourceWarning -m unittest discover -s r1-production-review -p 'test_*.py'`.
These tests use disposable executable fixtures, not Docker or the production host.

**November 16:** the original context check has passed. The next host command is
`scripts/r1-production-readiness-kali.sh`, which gathers missing deployment inputs
without rerunning tests. Unlike the original intake below, it reads Docker
environment values in local memory and exports only fixed-value comparisons,
variable names and an aggregate configuration fingerprint. It also records the
named data volume, Compose locations, all-container census and storage samples.
No production mutation or provider connection occurs. See [scope and remaining
delivery](../docs/R1-ENGINEERING-TO-PILOT-20261116.md).

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
