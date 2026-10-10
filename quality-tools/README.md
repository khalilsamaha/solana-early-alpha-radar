# Research quality helpers

These unchanged helpers come from research-quality 1.0.0. The scanner implementation is already present under `scanner/src/`; no patch installer is needed here.

Run `verify.mjs` with the running project's `.env` loaded, or run `run-report.sh` from the running project directory. See the root development guide. The report preserves missing/gapped/overdue outcomes and can optionally compare an existing observer export. It does not request quotes, send notifications or trade.

Offline test: `python3 -m unittest discover -p 'test_*.py'` from this directory.
