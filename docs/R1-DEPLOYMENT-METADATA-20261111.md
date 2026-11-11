# R1 deployment metadata — development validated, Kali capture pending

Date: 2026-11-11. The 152-test native-SOL accounting increment is now accepted
on Kali; see [its acceptance record](R1-NATIVE-ACCOUNTING-20261111.md). This
increment addresses a remaining source question: do the currently reported
deployment modification slots for Pump and Pump Fees precede the saved samples?
No actual deployment snapshot has been captured by the developer in this step.

## Why this is separate from accounting

The saved transactions at slots 468050019, 468049941 and 468049828 reconcile
internally. That cannot establish which executable version processed them or
which historical configuration supplied their fee rates. Current program
deployment metadata can help bound applicability; current fee settings cannot
be silently substituted for past settings. A program's upgrade slot also does
not freeze its separate mutable configuration accounts.

This probe reads only public loader-v3 program metadata and four ELF magic
bytes. It does not download/hash an executable, attest an SDK or source release,
read historical accounts, derive ProgramData PDAs, or validate all dependencies.
Its two-program scope excludes Token-2022, runtime features and other callees.
All broader version, bytecode, fee-configuration, curve reconstruction and
profitability acceptance flags remain false even on its most favorable result.

## Primary references and exact read plan

- [getMultipleAccounts](https://solana.com/docs/rpc/http/getmultipleaccounts): ordered account results, finalized commitment, minimum context and byte slices.
- [Program deployment](https://solana.com/docs/core/programs/program-deployment): Program-to-ProgramData indirection, modification metadata and next-slot activation for upgrades.
- [Loader-v3 state source](https://github.com/solana-labs/solana/blob/d9f20e951a06b61e4505da0955228020b96a8915/sdk/program/src/bpf_loader_upgradeable.rs): Program enum tag 2/36-byte layout and ProgramData enum tag 3/45-byte metadata, slot and optional authority. This is the source resolved from v1.18.26, not a claim about the current validator release.

The two fixed program IDs come from the existing hash-pinned `pump_schema.json`:
the Pump program ID and the buy_v2 fee-program account. The only endpoint is
`https://api.mainnet.solana.com`; no key, alternate provider or user-supplied URL.

| Request | Purpose |
| --- | --- |
| 1: getGenesisHash | Require the fixed mainnet genesis |
| 2: getMultipleAccounts, two accounts | Bootstrap both ProgramData pointers |
| 3: getMultipleAccounts, four accounts | Read both programs and both referenced ProgramData headers together |
| 4: getMultipleAccounts, same four accounts | Recheck pointers, headers and allocated sizes |
| 5: getGenesisHash | Recheck mainnet identity |

Every account request uses `encoding: base64`, `commitment: finalized` and
`dataSlice: {offset: 0, length: 49}`. The initial minimum context is the highest
sample slot; each later minimum is the preceding response context. Returned
contexts must satisfy those bounds. These are current finalized reads with a
lower bound, not historical-state requests. Program account data is exactly
36 bytes; ProgramData returns 45 metadata bytes plus the four-byte ELF prefix.

Both owner and executable flag, positive lamports, bounded allocated space,
canonical base64, exact slice lengths, enum/option tags, pointer identities and
ELF prefix are checked. Aliased roles are rejected. Last modification cannot be
in the future relative to its context. Metadata must agree across both final
snapshots. A hash of those 49 bytes is explicitly labeled as a header/prefix
hash, never as a bytecode digest. Pointer correspondence relies on the saved
RPC account order and contents; independent PDA/consensus proof is not claimed.

The preserved public-RPC transport limits each response to one MiB, each read
to at most five seconds within a thirty-second monotonic network budget, and
spaces requests by up to half a second. The new subclass allows only the two
read methods and at most five attempts. Redirects and inherited proxies stay
disabled. There is no retry or endpoint fallback. Failures use sanitized states;
provider error text and credentials do not enter reports.

## Input, output and result contracts

Before the first network request, the original accepted RPC report and bundle
must pass their checksums, source pins, exact request replay, schema comparison
and accounting consistency. Sample slots are taken from that validated result,
not from a caller-provided replacement slot or new scanner selection. There is
no Docker/database access, sudo requirement, wallet read, funding, transaction
simulation/submission, provider trade subscription or scanner change.

The exclusive private output directory contains `report.json` and
`evidence.json.gz`. The evidence binds the sample slots and original input
hashes to the exact new request/response sequence. A deterministic local replay
must agree before publication and after rereading retained evidence. All nine
executed source files are hashed before/after. The raw snapshot includes public
program metadata and public upgrade-authority addresses; it contains no wallet
secret or private API key. No observed live snapshot is committed to Git.

| Status | Meaning and next decision |
| --- | --- |
| deployment-metadata-predates-sample-live-blocked | Both reported modifications strictly predate all samples and rechecks agree. Retain this limited temporal evidence; do not promote it to binary/source or historical configuration verification. |
| historical-deployment-window-unresolved | At least one modification is at/after a sample. The current deployment cannot be assigned to all old samples. Assess historical evidence availability or a fresh capture pinned from its start. Do not retrofit current configuration into old evidence. |
| deployment-metadata-unavailable | Missing, inconsistent, unsupported or unavailable evidence. Preserve the report and reassess; do not automatically repeat traffic or change endpoints. |

Same-slot modification is deliberately unresolved because upgrades may become
effective in the following slot. Report per-sample comparisons without claiming
that a favorable program observation verifies the other program. No partial
metadata rows are exported as an overall pass after a failed recheck.

Exit zero means a diagnostic report was produced, including an unavailable
result. `local_replay_verified` means deterministic reproduction of retained
data; it does not authenticate that data against the chain. Offline replay
uses `--replay-evidence` instead of `--read-public-rpc`, the same original input
files and a different new output directory. It performs no network calls and
preserves the captured reconciliation rather than refreshing its eligibility.

## Validation

**167 tests passed**, zero failures/errors/skips, including 15 new probe tests
and the existing capture/restore rehearsal. The final runner used Python
3.12.14, SQLite 3.53.1, ResourceWarning as an error and internet socket creation
forbidden. It ran in 0.982760 seconds and pins 21 source files. Report SHA-256:
`d3d10dcf3a14fabb1f82ff15fed5f599dd94e422bae380cf6cea63eb8843b471`.

New tests cover exact request order/count/commitment/slices, context regression,
same/later modification, wrong genesis at both boundaries, malformed ownership/
encoding/size/tags, immutable authority option, altered pointers/headers/space,
future slots, forbidden methods, deadline/budget stop, HTTP failure without
retry or raw text, replay/input binding, private output and input preservation.
Unavailable captures are retained as explicit non-passes.

Integration used the real saved original inputs with five **mocked** public-RPC
responses whose contexts satisfied their sample slots. It passed capture,
retained replay and independent offline replay with socket creation forbidden.
This does not measure actual endpoint availability or real deployment metadata.
The unchanged accounting inspector also reproduced the uploaded Kali report
byte for byte, and original input bytes were preserved. No accepted inspector,
capture, transport or public-RPC base client was changed.

## Kali action and remaining R1 scope

From the pinned development checkout, run `r1-data/check.py`; only after it
passes, run `r1-data/deployment_probe.py --read-public-rpc` with the original
saved RPC inputs. Upload the offline report plus the new probe's `report.json`
and `evidence.json.gz`. No fresh transaction sample, wallet/API key or sudo is
needed. An unavailable probe is useful evidence and must not be represented as
a version pass. Kali offline/capture acceptance is pending.

After review, make the source-version applicability decision explicitly. The
broader remaining requirements are historical configuration/executable pricing,
source ordering and early-event gaps, provider connection coexistence, actual
network-adapter validation, off-machine preservation and a numeric funding/
billing decision before any paid activation. Favor a concrete feasibility
verdict over accumulating additional arithmetic diagnostics. The original
five-working-day build/validation effort cap is unchanged; incomplete evidence
at the endpoint leads to a limited/incomplete verdict, not an automatic extension.

The current work is a development-branch increment only. Full-gate Kali
validation precedes PR/CI consolidation; merge still requires the agreed owner
decision. No production deployment, restart, signing, funded trade, ML fit or
profitability claim is authorized by this probe.
