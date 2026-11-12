# R1 draft measurement contract and offline evaluator

The preceding isolated service integration is accepted on Kali at
`a0003221ac794ee0741a1908f23c2a0524dd65cc`: 314 core, 21 lifecycle and 16
integration tests, 142 matching source hashes, real Unix IPC, actual disposable
container restart-policy changes, and all six disposable containers removed.
Both lifecycle journals and both complete session packages independently replay
exactly. Full Kali runner: 36.87488 seconds. Production was not modified.

This increment prepares the measurement contract required before a live pilot.
It does not close production handoff, provider/TLS validation, funding/exposure
approval, real-session retention or the full R1 gate. It does not enable ML,
trading, signing, a wallet connection or paid subscriptions.

## Draft terms

`proposal.json` is an explicit **draft-unapproved** contract. Its limits match
the existing capture defaults exactly: 20,000 counted messages, 8 MiB raw data,
48 hours maximum, 64 KiB/frame, SHA-256(mint) modulo 64 sampling, two concurrent
watches, 24 admitted watches per day and 600 seconds per watch. Any terminal
limit stops collection; reaching 24–48 hours is not guaranteed or required.
Message counts are not billed-message counts and do not enforce a fee ceiling.

The new local-quality criteria are preliminary engineering decisions, fixed
without inspecting trading outcomes:

| Criterion | Draft threshold | Meaning |
| --- | --- | --- |
| Selected creations | At least 24 | One full default daily admission allotment; an engineering floor, not statistical power or population coverage |
| Local receive-to-send-return | Maximum 1,000,000,000 ns | A proposed local delay ceiling; includes capture-thread queue consumption through local send completion, excludes upstream-to-queue delay |
| Recorded gaps | Zero | A gap fails this clean-session criterion; missing unobserved events may still exist |
| Abandoned sends | Zero | Failed/abandoned admission cannot be hidden |
| Unresolved sends | Zero | Every intent must have an observed terminal result |
| Selected creations without completed local send | Zero | Completion fraction uses selected creations as its denominator |
| Session outcome | `capture-stopped` | Cleanup failure, cancellation or transport failure fails local quality |

The one-second ceiling is not a provider SLA, subscription acknowledgement or
proof that initial trades were captured. It is not derived from the synthetic
fixture's latency and is not a profitability criterion. The minimum sample and
ceiling must be reviewed before activation. Retuning requires a new source-bound
contract; changes cannot be silently applied to already-collected data.

The current collector's replay contains no independently established provider
subscription acknowledgements, external creation denominator, initial trade
coverage, billed-event count or actual fees. Those fields stay **null**, never
zero. Ledger order and finality remain unverified. Unknown remote facts cannot
be inserted into this local-only evaluator; a separately reviewed reconciliation
adapter would be needed to support them.

## Verdicts and authority

- **Local quality:** fail for an observed failure; otherwise insufficient below
  the sample floor or with capture limits different from the contract; otherwise
  pass. An observed failure takes precedence over insufficient sample size.
- **Source adequacy:** insufficient with the current local evidence.
- **Measurement gate:** fail on local failure; otherwise insufficient while the
  provider/source requirements remain unresolved. A local pass cannot clear it.
- **Activation:** always blocked. Funding, intended fees and approved exposed
  balance remain null; owner approval, retention acceptance, production rollout
  acceptance and live authority remain false.

The earlier 0.05 SOL funding and 0.02 SOL fee figures remain unapproved proposals
in the feasibility document. No numeric spending authority is inferred here.
There is no approval-writing command or live launcher in this package. Editing
approval flags, limits or thresholds in JSON alone is rejected against the
reviewed source contract. This is a code guard, not protection from an operator
changing both code and data; there is no cryptographic owner signature.

## Binding, replay and provenance

`freeze()` creates a private, exclusive `contract.json` containing the exact
proposal, all implementation source hashes and their digest. The review requires
its exact SHA-256, rejects duplicate keys/noncanonical content and refuses source
drift or file replacement. This is a frozen draft for review, not an approved
study registration. Hashes are integrity bindings, not trusted timestamps.

`review()` takes a contract hash and complete-session archive hash, uses the
existing bounded private restore/replay, and reads actual capture limits from
the replayed journal's start record. It does not trust caller-supplied metrics,
labels or limits. The result binds both hashes and includes observed denominators
and timing scope. Existing data can be reviewed retrospectively, but
`precollection_registration_proven` remains false: neither a SHA nor the local
clock proves this draft governed a past collection. Future live integration must
bind admission to an approved registration before opening the collection window.

The local evaluator supports the current shared-session journal, whose local
commands are research subscription sends. Broader command/provenance formats
must receive a versioned review rather than being silently coerced.

## Kali check

Run `check_registration.py --output-directory NEW_PRIVATE_PATH` using the pinned
wire dependency. It performs 314 core and 18 contract tests and two native Node
pipe scenarios. It freezes its draft before generating those synthetic fixtures,
then restores/replays each archive and evaluates it. No Docker operations,
production restart, provider traffic, credentials or remote backup occur.

Expected runner status: `offline-measurement-contract-passed-live-blocked`.
The normal four-row fixture must evaluate **insufficient** (small sample and
different synthetic limits), and the deliberate cleanup failure must evaluate
**fail**. Those are expected evaluator results, not failures of the checker.
The unit suite also demonstrates a 24-creation local pass that remains globally
insufficient and cannot acquire live authority.

Upload `report.json` and `contract.json`. No repeat Docker or B2 rehearsal is
requested for unchanged components. After Kali validation, the remaining work
is production admission/rollout and real-session preservation integration, plus
review of the complete measurement and numeric-exposure terms before live use.
No ML action is needed. The existing five-working-day total R1 engineering cap
is unchanged; this increment does not reset it or assert a new allowance.
Full-gate Kali acceptance precedes PR/CI consolidation and an owner-approved merge.
