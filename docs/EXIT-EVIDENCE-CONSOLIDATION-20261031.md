# Exit evidence and signing handoff consolidation — 31 October 2026

This batch combines three host-accepted internal increments:

| Increment | Kali acceptance (UTC) | Portable cases |
| --- | --- | --- |
| Bounded admission-owned exit collector | October 31, 06:05:55 | 19 |
| Atomic collected preparation and provenance replay | October 31, 17:39:33 | 21 |
| Durable exit signer-adapter handoff and recovery | October 31, 17:55:29 | 21 |

Each public report was replayed against its pinned source, including all flags.
The batch preserves exact acquired inventory, retained fee commitments and the
original collection deadline. It adds no runtime deployment, automatic retry,
allocation release, wallet backend or transaction sender. Public reports remain
observational and cannot be imported as signing authority.

Local targeted validation passed before publication: 78 tests for the final
handoff increment, including its 21-case portable CLI, plus the collector and
persistence tests recorded in their scope documents. The consolidation PR runs
all five existing CI groups; merge requires their success at the final head.
No test partition or assertion has been removed from the existing full suite.

The next increment connects a separately restricted devnet exit key backend to
the saved request. One-send submission/recovery and final receipt, residual-balance
and allocation reconciliation remain after it. No live execution is part of this
consolidation. The fixed confirmation study and November 6 review remain unchanged.
