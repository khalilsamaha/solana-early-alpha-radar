# Engineering consolidation — 29 October 2026

The preceding observation base was merged in PR #58 at
`07d72772f7379b4f726b2eb1caa1945f661bfbe3` after its exact-head CI passed.
This next batch consolidates the frozen failure diagnostic, the separately
registered availability confirmation, reverse observation and independent paired
cost scenario. It does not deploy changes to the scanner or authorize execution.

## Accepted evidence

- The frozen diagnostic replay preserves the original model/report identities,
  forward counts and fixed-threshold partitions. It does not promote a model.
- The availability confirmation uses unchanged early-activity weights and
  threshold for October 30–November 5 UTC. Review remains November 6, 00:05 UTC
  (01:05 Amsterdam); preserve captures November 1, 3, 5 and 6. No timer or
  admission changes are introduced. The private registration is authoritative.
- Reverse and paired host observations passed their intended independent-leg
  gates. The paired sample shows entry 1,000 → 998 and reverse 998 → 996,
  5,000-lamport fees each, 30,000-lamport modelled cap budget with one additional
  failed-exit allowance, and no shortfall. The expired first quote stays labelled.
- Public summary review is not independent replay of omitted raw RPC or private
  journals. Two independent simulations are not a sequential executed round trip.

## Validation

Local release checks passed: 1,509 core tests (1,164 Python and 345 Node),
266 devnet-pool tests and 55 ML/forward/availability tests: **1,830 total**.
The ML environment used numpy 2.3.5, scipy 1.17.0 and scikit-learn 1.8.0.
Source hygiene and whitespace checks pass. The consolidated PR supplies the
shared CI checkpoint under the agreed local-tests-first workflow.

## Next engineering boundary

Review the pool account returned by the same unsigned entry simulation, including
exact protocol/fund fee accrual and immutable bytes, then derive a reverse amount
from those simulated effective reserves using exactly the acquired quantity.
Start with a pure offline contract and adversarial fixtures; integrate a distinct,
bounded nine-account collector afterward. Keep existing eight-account and paired
observers unchanged. Never label a fabricated capture as a fresh RPC observation.

No scanner rebuild, service restart or repeated paired host check is necessary
for this consolidation. Actual post-entry state, validated exit execution,
mainnet-specific account/route checks and a separately scoped funded pilot remain
uncompleted gates. Strategy profitability is not established.
