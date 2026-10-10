# Research quality helpers

The report-2 update adds actual checkpoint delays, same-time versus earlier signals, follow-up-policy groups, common complete cohorts and matched endpoint price comparisons. Historical links without a comparison entry price stay unavailable.

Run verify.mjs with the running project environment loaded, or run run-report.sh from the existing host project directory. The helper uses a bounded read-only database snapshot and can optionally read an existing quote export. It does not request quotes, notify or trade.

The compact shadowSummary remains available; detailed results are in evidenceAnalysis. Eventual-link and complete-path groups use hindsight and must not become entry filters. Old and new follow-up policies are grouped separately.

Offline tests: python3 -m unittest discover -p 'test_*.py'
