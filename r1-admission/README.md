# R1 admission, supervised session and recovery candidate

This increment joins the accepted reusable session/archive to frozen draft
admission, a stable consumed registry, sealed credential delivery and an actual
bounded child process. It generates synthetic input only. It adds no provider,
credential-path, arbitrary-command, production-target or live CLI argument.

## Connected sequence

1. Require a fresh private output and a separate private registry. Hold the
   existing cooperating-process registry lock throughout the attempt. Freeze the
   existing measurement draft and write a canonical request binding its hash,
   exact implementation fingerprints, fixture limits, resource profile, registry,
   output, parent PID and attempt identity. Consume the durable registry claim
   before credential loading or worker startup.
2. Generate a synthetic credential in a private temporary directory and use the
   existing private-file validator and sealed anonymous descriptor delivery. Only
   a descriptor number goes to the fixed child; the input file is removed and the
   parent's descriptor closed. No real credential is loaded. The worker requires
   the generated sentinel format, consumes/closes the descriptor and passes its
   redaction variants to the actual Wire wrapper around an in-memory peer.
3. Revalidate the request, frozen draft, source and registry in the child before
   running the accepted session library. The existing Linux bootstrap enforces
   parent-death SIGKILL with PID recheck, no core dump, 256 MiB address space,
   five CPU seconds, 44 MiB/file, 32 descriptors and a ten-second alarm. Internet,
   DNS and child-process creation are denied in that worker. The parent gives it
   at most 12 seconds, then performs bounded TERM/KILL/reaping. No timer is extended
   or converted to a 24–48-hour live policy.
4. In default Kali mode, a separate native Node scanner consumer connects to the
   real Unix socket before any synthetic upstream is opened. The parent checks
   exact discovery counts/source names and zero consumer upstream connections.
   Explicit development mode uses the existing simulated endpoint and cannot
   satisfy native Unix acceptance. There is no fallback from default to development.
5. The child closes the session and creates the existing complete archive. The
   parent requires child exit zero, successful consumer completion, exact worker
   receipt/request/draft/limits bindings and independent archive replay/restore.
   Both processes must be reaped before a successful supervisor receipt. Source,
   request and registry bindings are checked again before receipt publication.

The run preserves its request, frozen draft, source capture, journal, admission,
stop receipt, archive, parent restore and terminal supervisor receipt. A failed
credential load, spawn, diagnostic, signal, timeout, replay or source check leaves
its claim consumed. A new output directory or draft cannot reuse that registry.
No cleanup removes run evidence or a consumed claim.

The lock only coordinates callers using that same registry. A caller choosing a
new registry, deleting evidence or changing code can bypass that scope. It is not
host/IP-wide ownership enforcement, authentication or cryptographic approval.
Synthetic fixture limits deliberately differ from the draft measurement defaults;
binding that draft here grants no live or precollection approval.

## Diagnostics, failures and recovery

Child stdout/stderr are discarded to avoid persisting credential-bearing errors.
Within the worker, stderr is captured privately through session execution and
archive export. The accepted diagnostic matcher makes resource/runtime/async
warnings fail completion, including shielded-future diagnostics. No raw diagnostic
or secret value is returned to the parent. The parent retains fixed failure stages
and exit status, not exception text. This is not a promise of memory zeroization.

Normal and idle scenarios produce capture-stopped evidence. Cleanup failure
produces complete evidence with transport-cleanup-failed; successful supervision
never turns that session into a clean capture. A deliberate stalled child dies at
its existing SIGALRM limit. A deliberate secret-bearing diagnostic exits nonzero
without a worker receipt/archive. Both write a request-bound fault-ready marker
first, so unrelated early startup failure cannot pass their fault checks.

`admission.inspect(registry, output)` performs read-only evidence recovery. It
spawns nothing, writes no run files, invokes no transport and grants no restart.
Missing supervisor receipt means admitted-outcome-unconfirmed. A failed receipt
means failed-reconciliation-required. A successful receipt must still match its
request, draft, source and independently replayed archive. Inspection reports
recorded evidence, never a fresh observation of a host process or provider socket.
A complete offline verdict keeps automatic resume and live authority false.

## One consolidated Kali check

`scripts/r1-admission-kali.sh` runs only the new integration tests and five retained
scenarios: normal, cleanup-failure, idle, stall and tainted-diagnostic. The three
session scenarios use actual native Node/Unix in default mode. Fault scenarios
must reach their specific marker and expected exit status, remain failed, and
require reconciliation. All workers/consumers must be reaped. Each case is checked
through the read-only recovery path. An unchanged 160-test session batch is not
repeated; its accepted source fingerprints are preserved by this new package.

Return one `acceptance.zip` containing report/log, all five request/claim/draft/
supervisor sets, fault-ready markers, and three exact worker receipts/archives.
Originals and parent restores remain beside it. No remote upload or retention
change occurs. On failure retain the whole directory and return report.json plus
validation.log; do not reuse a consumed registry.

Default success: `admission-offline-passed-live-blocked`.
Development success: `admission-development-passed-unix-pending`.
Neither status is full R1 acceptance.

## Remaining boundary

This closes a connected offline admission/supervision/recovery implementation gap.
It does not implement the eight-step production service handoff. The existing
service lifecycle coordinator still accepts synthetic handoff receipts only; this
package neither fabricates those receipts nor changes the running direct scanner.
Joining actual direct-owner shutdown, shared activation and explicit rollback to
this supervised session remains a separately reviewed production integration.

A fresh read-only production identity/ownership inventory, approved long-running
supervision profile, credential provisioning, live preservation/retention/capacity,
fixed measurement terms and numeric exposure authority remain required before a
real provider pilot. No B2 rehearsal, trading, funding, signing, main merge or
production deployment follows. E0 stays independent and held. The five-working-day
engineering cap is unchanged; no remaining allowance is asserted or reset.
