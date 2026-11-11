# R1 documented TradeEvent comparison — Kali accepted

Date: 2026-11-11. This continues the existing R1 source-feasibility work within
its five-working-day build/validation cap. It does not open a new gate or extend
that cap. The previous strict event-inspector increment remains Kali accepted.

## Finding

A newer published TradeEvent definition explains both saved 390-byte payloads
under an explicitly separate diagnostic profile. The docs.rs source labeled
`pump-rust-client` 0.5.0 has 36 ordered fields: the previous 35 match exactly,
followed by `quote_transfer_fee: u64`. Both saved events consume and re-encode
all 390 bytes with the new profile. Both report zero in the new field, and the
decoded mint/user/buy direction/token/SOL/quote quantities agree with the
separately parsed transaction evidence.

This is a documented byte-layout and transfer agreement, not proof of the
deployed program version, historical activation range, fee semantics or a
complete economic reconstruction. The default `event_inspect.py` and its
`pump_schema.json` remain byte-for-byte unchanged and still report eight unknown
bytes for these events. No permissive fallback or automatic schema selection
has been introduced into that accepted inspector.

| Saved case | Old profile | New diagnostic profile | Reported quote transfer fee | Name observations |
| --- | --- | --- | ---: | --- |
| 1 | 382 bytes consumed, 8 unknown | 390/390 consumed and re-encoded; transfers agree | 0 | parent buy_v2, event buy |
| 2 | No trade event in this transaction | No trade comparison | Not applicable | Not applicable |
| 3 | 382 bytes consumed, 8 unknown | 390/390 consumed and re-encoded; transfers agree | 0 | parent buy_v2, event buy |

The names are preserved literally; an alias or mapping is not certified. This
three-transaction sample does not establish general coverage. The Mayhem case's
two MintTo operations and event supply difference remain separate observations.
SOL paid to the curve still excludes additional transfers, rent and transaction
fees; it is not total acquisition cost.

## Source investigation and provenance limits

The official public-docs JSON histories checked were:

| Revision | TradeEvent fields | Last field |
| --- | ---: | --- |
| e0687ae9b7e064a0f54efc7297c65eecfbba3a8f | 34 | holder_rewards |
| 8cda1fa30ea658b20909d8aedf002047119388d2 | 35 | creator_fee_unclaimed |
| 2293f9a66c654e9fe82dc5e8f4618538f24bb35f | 35 | creator_fee_unclaimed |
| 639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22 | 35 | creator_fee_unclaimed |

Repository: https://github.com/pump-fun/pump-public-docs

The latest checked JSON and TypeScript layouts agree after normalizing naming
case. `creator_fee_unclaimed` is already in our accepted 35-field profile and
cannot be appended again as a repair. For all five saved create/trade events,
the CPI event payload equals its Program-data log copy exactly after removing
the separate eight-byte Anchor CPI tag once. That wrapper is not the eight-byte
schema remainder. Log duplication is not independent chain authentication.

The official public-docs README links `pump-rust-client`. Its docs.rs pages,
retrieved 2026-11-11, display version 0.5.0 and report a 2026-10-19 release:

- Embedded IDL: https://docs.rs/crate/pump-rust-client/latest/source/idls/pump.json
- Event fields: https://docs.rs/pump-rust-client/latest/pump_rust_client/pump/pump/events/struct.TradeEvent.html
- Source revision: https://docs.rs/crate/pump-rust-client/latest/source/.cargo_vcs_info.json
- Package metadata: https://docs.rs/crate/pump-rust-client/latest/source/Cargo.toml
- Version history: https://docs.rs/crate/pump-rust-client/latest

The embedded IDL's complete TradeEvent definition was extracted mechanically
into `r1-data/trade_profile_0_5_0.json`, with retrieval date and provenance. Its
SHA-256 is `500612a20b6829dfdd3475290af27ed8d6450df99adb27ea366fed2669fe214b`.
The page reports VCS revision `462f90a16b1ce666fcb858d5e195f7f49f14b33a`.
Shareholder remains address/pubkey plus share_bps/u16. No field was inferred
solely from payload length or a third-party issue comment.

These are mutable `latest` URLs: local hash pinning preserves the extracted
definition, not an immutable upstream archive. Version-specific/archive
retrieval was unavailable in this review. No crate checksum, source checkout at
the reported VCS revision, deployed binary or activation history was verified.
No SDK was installed or executed. Those limits remain explicit in the report.

## Comparator contract

`schema_compare.py` first runs the unchanged strict inspector's full input
replay/provenance/transfer checks. It then compares only supported direct native
SOL buy_v2 TradeEvents with the new pinned profile. Every byte must decode and
re-encode, and identity/direction/transfer fields must agree. Extra or missing
bytes, profile changes, unsupported provenance and conflicting evidence cannot
produce a match. A nonzero new field can be reported literally but never grants
fee-model acceptance. Unsupported cases export no partial decoded values.

The CLI rechecks compressed and decoded evidence hashes, source pins and input
bounds, preserves inputs, and writes a private atomic report without replacing
an existing path. It exports payload hashes and narrow diagnostic values, not
wallet/mint/signature identities. Exit zero means a report was created; inspect
case states. Network, credentials, paid collection, deployed-version validation,
fee-model validation, reconstruction and profitability flags remain false.

## Development validation

All **137 tests** passed, zero errors/failures/skips, including 11 new comparator
tests and the existing capture/restart/export/restore rehearsal. ResourceWarning
was treated as an error. The standalone runner pins 17 files and took 0.768875
seconds on the development runtime; this is not a Kali or latency measurement.

The new tests cover exact layouts, nonzero 64-bit extension values, signed
timestamps and shareholders, every extension truncation, extra bytes, identity
and amount conflicts, unsupported provenance, unchanged default mismatch,
literal instruction names, source/profile/replay pins, network prohibition,
input/output preservation, checksum/decompression limits and sanitized failures.

The real saved bundle also ran with socket creation forbidden. Inputs were
unchanged, and the default inspector replay was byte-identical to the accepted
Kali report. New comparison report SHA-256:
`4691cb703df8bd7c6058144db1f747326593f0555ba323b8e23ae9f8578a3c38`.
Development runner report SHA-256:
`92a1a9eba4df6f8454f73b41c743fb7ee0109789e1e9abce60c59098db5e3355`.

Input RPC report SHA-256:
`dcaf55dece8e1e53455b291340912bb03aec32d0093ce803f0f8ed1ac9434e66`.
Compressed evidence SHA-256:
`29ffa7dff87dc6d9ba29c81878d4540a943d4b9f8e993612d39cfba37a60e7ef`.
Decoded evidence SHA-256:
`ede0a9787d9adb0fa1d5ad238a6b76e3705d3e6321560dfbc83a178b81248a46`.
Private input and report artifacts are not added to Git.

## Kali review and next engineering boundary

From an independent checkout pinned to the published development commit/tree,
run `r1-data/check.py` and `r1-data/schema_compare.py` on the existing saved RPC
files. Expected runner: `offline-schema-comparison-passed-live-blocked`, 137
tests, no failures/errors/skips. Expected comparison:
`offline-schema-comparison-complete-live-blocked`, two exact diagnostic matches
and one no-trade-in-this-transaction case. Upload those two reports for review.
Kali acceptance is pending, not inferred from development success.

After that acceptance, the next bounded investigation is native-SOL fee/reserve
accounting against these saved transaction instructions and documented fields,
with historical version applicability kept explicit. No broad reconstruction,
ML fit or profitability claim follows from a byte match. The five-working-day
R1 limit and separate provider coexistence, adapter, preservation and numeric
funding/billing requirements remain unchanged. Development-branch upload only;
full-gate Kali acceptance and the agreed owner decision precede PR/CI
consolidation and merge. No funding, transaction, scanner restart or deployment
is part of this increment.

## Kali acceptance, 2026-11-11

Reviewed development commit `5d640392012cf3e5ee118f405b76751e1301d86a`, tree
`f1835173a636e4111a6d8d813bd3014c6043e092`. Uploaded evidence:

| Artifact | SHA-256 |
| --- | --- |
| radar-r1-schema-offline-20261111T085934Z-342484.json | c11ec927d73f502dae5066c67885b548345d9fee6e8f5428209722ade100e43e |
| radar-r1-schema-comparison-20261111T085934Z-342484.json | 4691cb703df8bd7c6058144db1f747326593f0555ba323b8e23ae9f8578a3c38 |

The Kali runner reports 137 tests, zero errors/failures/skips, Python 3.14.6,
SQLite 3.53.4 and 1.562522 seconds elapsed. Local capture restore/replay and input
preservation passed. All 17 runner source hashes and seven comparator source
hashes match the reviewed implementation. The reviewer independently replayed
the original saved RPC inputs with socket creation forbidden; the complete
comparison report is byte-identical to the uploaded Kali report.

Both 390-byte trade layouts and re-encodings match; case 2 remains scoped to no
trade in that transaction. All historical-version, fee-model, reconstruction,
profitability and live-collection non-acceptance flags are retained. Accept this
offline comparator increment on Kali; this does not close full R1 or authorize
PR/CI consolidation, funding or deployment. Next: the separate bounded native
accounting inspection in [R1-NATIVE-ACCOUNTING-20261111.md](R1-NATIVE-ACCOUNTING-20261111.md).
