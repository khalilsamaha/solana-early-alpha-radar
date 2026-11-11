# R1 offline creation-event inspection — Kali pending

Date: 2026-11-11. This is the fourth R1 feasibility increment, not a new study or
gate. The previous RPC increment is accepted on Kali. This code is development
validated; its own Kali acceptance remains pending.

## Result and engineering decision

The three saved creation transactions contain three exactly decodable CreateEvent
payloads and two TradeEvent payloads that the pinned official IDL does not consume
completely. Both trade payloads are 390 bytes excluding the Anchor event tag; the
pinned layout consumes 382 bytes and leaves **eight unconsumed bytes**. Even an
all-zero remainder is not accepted. This does not prove that a new field was
appended: a schema divergence elsewhere is also possible. No partially decoded
trade fields are exported, and their fee/reserve interpretation remains blocked.

Separately parsed SPL/system instructions show purchases inside creation
transactions 1 and 3. Those transfers can be observed without assigning meaning
to the unsupported TradeEvent payload. There is no purchase event in transaction
2 under the supported direct-instruction layout; this says nothing about later
transactions, missing subsequent feed events or the token's lifetime trading.

| Case | Create event | Mayhem flag | Creation MintTo operations | Sum of minted base units | Same-transaction token transfer | SOL transfer to curve, lamports | Trade schema |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | Exact layout | true | 2 | 2000000000000000 | 34199203154141 | 987654320 | 8 bytes unconsumed |
| 2 | Exact layout | false | 1 | 1000000000000000 | None observed | None observed | No trade event in transaction |
| 3 | Exact layout | false | 1 | 1000000000000000 | 7018806171954 | 197530863 | 8 bytes unconsumed |

All three creation events report token_total_supply 1000000000000000, virtual
token reserves 1073000000000000, virtual SOL reserves 30000000000 and real token
reserves 793100000000000. These are decoded event values, not independently read
historical curve account states. In case 1, event supply and MintTo total differ;
the inspector preserves both. Neither quantity is assumed to be the universal
supply model. Six token decimals come from the already accepted mint evidence.
SOL-to-curve transfers exclude fee transfers, rent and transaction fees: they are
not total acquisition costs. No economic reconstruction is accepted.

## Pinned schema and provenance

Official source:
https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/idl/pump.json

`r1-data/pump_schema.json` mechanically retains the program address, CreateEvent
and TradeEvent discriminators, their ordered fields, Shareholder fields, and the
create_v2/buy_v2 account names and fixed addresses. Schema SHA-256:
`5f363ffd904f53f9330df55ad926e89bb21ec37719df0c9ede73cfb889e8571d`.
The inspector requires that hash. The upstream metadata version alone (0.1.0) is
not a unique version identifier. Pinning the upstream commit identifies the
documentation snapshot; the deployed program binary and upgrade history have not
been reconciled to it.

Supporting primary references:

- https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/docs/instructions/COIN_CREATION.md
- https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/docs/instructions/BUY.md
- https://solana.com/docs/programs/anchor-events
- https://www.anchor-lang.com/docs/features/events

Only direct SOL create_v2/buy_v2 parent layouts are recognized. Event provenance
checks require the Pump program ID, known parent discriminator and account layout,
Anchor event tag, event discriminator, direct self-CPI stack height and matching
parent event authority. Parent arguments are not decoded/certified. Pubkey roles
are checked against transaction membership and fixed addresses; PDA derivation
and cryptographic authentication are not claimed. Duplicate log copies are not
counted twice. Missing/duplicate events, unknown tags, extra accounts and CPI
wrappers remain unsupported. A successful transaction does not override an
unsupported event layout.

## Validation and retained evidence

Input is the already accepted uploaded bundle, compressed SHA-256
`29ffa7dff87dc6d9ba29c81878d4540a943d4b9f8e993612d39cfba37a60e7ef`,
decoded SHA-256
`ede0a9787d9adb0fa1d5ad238a6b76e3705d3e6321560dfbc83a178b81248a46`.
RPC report SHA-256:
`dcaf55dece8e1e53455b291340912bb03aec32d0093ce803f0f8ed1ac9434e66`.
The original inputs were not changed or added to the Git repository.

The new inspector verifies input hashes, source pins, RPC replay and request
accounting before decoding. Reads, decompression, payloads, strings and vectors
are bounded; output is private, atomic and refuses replacement. It exports
sanitized counts, integer quantities and payload hashes, not token metadata,
mint/signature identities or wallet addresses. Exit zero means a diagnostic
report was produced; the report still declares reconstruction and live collection
blocked, including when every supported event matches its schema.

Development validation passed **126 tests**, zero failures/errors/skips, including
25 new inspector tests and the capture/export/restore rehearsal. Python 3.12.14,
SQLite 3.53.1, ResourceWarning treated as an error; standalone runner 0.680611 s.
The runner pins 14 source files. Tests cover exact decoding, every CreateEvent
truncation point, unknown tails, invalid booleans, large integer precision,
string/vector/decompression caps, CPI provenance, missing/duplicate events,
transfer identity, distinct supply observations, checksum/source/replay failures,
private output and preservation. These are offline tests, not new RPC measurements.

Running against the real uploaded bundle with socket creation forbidden produced
the identical report. Inspector report SHA-256:
`496b50fea61c0928d9cda8e6a846740f91d08c27a8115900378df3de5db943d6`.
No fresh RPC request, provider credential, outcome read, wallet action or scanner
change was used. The accepted capture, transport, source-probe and RPC-probe
implementations remain unchanged.

## Required next decision

Run the pinned offline acceptance runner and inspector on Kali using the existing
RPC files. Upload both new JSON reports; no public RPC rerun is required.

Resolve the exact TradeEvent layout against an authoritative program/schema
version before fee/reserve decoding or curve reconstruction. Preserve unknown
bytes; do not silently truncate, pad, reinterpret or fit fields to expected
economic values. This is now a concrete source-feasibility blocker, not a passed
reconstruction milestone. The five-working-day R1 build/validation cap is not
extended by this increment. Provider connection coexistence, live-adapter
validation, preservation and explicit funding/billing approval remain separate
open requirements. No paid activation, ML fitting, PR/CI consolidation, merge,
deployment or restart is authorized by these findings.
