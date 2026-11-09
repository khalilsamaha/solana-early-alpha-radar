# Project timeline — November 8, 2026

**Historical estimate:** the [independent review and working agenda](PROJECT-AGENDA-20261108.md)
now governs priorities and dated checkpoints. The estimates below describe the
earlier execution-first sequence, not a trading-launch commitment. PR #79 and
all 12 post-merge checks have since completed successfully.

## Current position

The full uninstrumented Kali gate passed all 42 checks at 08:07:13 UTC with
1,343 ms of positive deadline headroom, including recovery, preservation and
cleanup. Phase consolidation is now in progress. The prior 53 ms failure remains
relevant to timing variability; actual-provider readiness is not established.
See [the consolidation record](SUCCESSOR-CONSOLIDATION-20261108.md).

The engineering objective is a finite, reconciled controlled-devnet exit from
the held position, with conservative accounting and recovery. Scanner research
collection and execution are separate tracks. The completed frozen-model study
did not promote a strategy; the later availability study was insufficient under
its registered criteria. These decisions are not reset by engineering progress.

## Planning ranges

These are estimates of active engineering time starting November 8, assuming
prompt host runs/uploads. They are not promised delivery dates. A failed gate
returns to diagnosis and moves every dependent item; elapsed days cannot clear it.

| Order | Work and acceptance evidence | Planning range | Dependency |
|---|---|---|---|
| 1 | Validate lifecycle replay correction on Kali: all 42 cases, positive original-deadline headroom, recovery, preservation and cleanup | Completed November 8, 08:07 UTC | Functional offline acceptance only; preserve the earlier failed run |
| 2 | Consolidate the completed diagnostic/performance phase; full repository regression, review, required PR CI, merge and post-merge verification | About 1 working day after gate 1 | No per-increment PR/CI before full Kali acceptance |
| 3 | Prepare and validate a separately scoped operational successor command; assess real-provider latency and authorize one bounded devnet attempt | 2–4 working days after the accepted base | Offline timing is necessary but does not include provider latency; a failure may consume the attempt and require observation/recovery |
| 4 | Implement/validate exact successor receipt accounting, fresh residual balances, durable scoped closure and interrupted/idempotent recovery | 2–4 working days, partly preparable with gate 3 | An RPC acknowledgment or finalized claim alone cannot release holds; requires exact receipt/effect evidence |
| 5 | Consolidate the complete devnet exit/closure phase and verify operational recovery documentation | About 1 working day | Kali acceptance of the complete cycle, then full regression/CI/review |
| 6 | Decision-focused review of existing compatible quote evidence; choose whether a new economic hypothesis merits prospective testing | 1–2 working days; independent preparation may overlap engineering | Keep source versions/cohorts separate and preserve failures, exclusions and original closed-study decisions |
| 7 | If justified, freeze a new protocol and collect untouched prospective evidence | Several weeks or longer; duration/sample guards must be registered before collection | No reused holdout, relaxed thresholds or calendar-only pass; data arrival may leave the result insufficient |
| 8 | Any funded mechanics test or strategy pilot | No committed date | Target-route validation, full costs, bounded risk, execution/recovery acceptance and separate funding authorization; a strategy pilot additionally needs credible prospective economic evidence |

The near-term planning envelope for the engineering sequence is roughly one to
three weeks, conditional on consolidation, operational timing and actual
devnet evidence. This is not a mainnet/trading launch forecast. Mainnet aggregator
routes, liquidity/account behavior and costs are not proven equivalent to the
controlled direct-pool devnet route.

## Working agreement

Push tested development commits as needed to make pinned tools available on Kali.
Provide complete fetch/checkout/run commands using the separate development
checkout and the existing project directory. Review host output before advancing.
Consolidate only after the complete engineering phase/gate passes on Kali, then
perform its full-check/CI/merge cycle. A push or merge is not a deployment.

Do not widen the ten-second freshness limit, reset attempts, erase predecessor
journals, release unresolved reservations or infer performance acceptance from a
faster development host. Preserve the failed reports as evidence. Re-estimate the
timeline after each host gate rather than promising a profitable launch date.
