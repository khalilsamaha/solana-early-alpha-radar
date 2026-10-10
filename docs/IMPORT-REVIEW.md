# Initial source import review

Source: `radar-source-review-20261009T215929Z-1282958.zip`, captured 2026-10-09 at 21:59:29 UTC.

All 113 captured source files matched `SOURCE-REVIEW-MANIFEST.json`. They are imported byte-for-byte. No `.env`, runtime databases, live reports, rclone configuration, private heartbeat URL or wallet material was included. A credential-pattern scan found no matches; this is not a guarantee that every possible secret format can be detected.

The deployed scanner matches the previously validated source except for the host heartbeat helper and the deployed PumpPortal correction: public WebSocket URL and sanitized subscription error details. These deployed changes are preserved.

Additional files:

- Regression tests restored from the validated checkpoint, statistics-memory, statistics-worker and research-quality packages. Test imports were adjusted where necessary for the `scanner/test/` location.
- Quality reporting helpers from research-quality 1.0.0, so the new evidence can be inspected from a checkout.
- `quote-observer/replay-results.json`: historical aggregate restored from the original observer 0.5.0 package, matching its existing manifest hash. The source exporter omitted it because it selects source extensions. It contains counts and aggregate research results, not raw live evidence or credentials. It is not a current performance report.
- Repository CI, source hygiene checks, roadmap and release manifest.

The import changes no scanner implementation, signal eligibility, polling, notification configuration, observer budget or deployed host state. It does not migrate production to Git and does not introduce trading.

## Known limitations

- Existing component documentation was retained for provenance and can reference older layouts or missing example `.env` files. Use the root development guide for this repository.
- The Docker base tag remains the deployed `node:24-bookworm-slim`; this import does not freeze the image digest. A later release process should record and validate its runtime image digest.
- The quote observer ledger is separate from the scanner database and still needs its own scheduled backup/restore coverage.
- CI runs offline tests; it cannot establish live provider freshness, sustained host stability or executable profitability.
