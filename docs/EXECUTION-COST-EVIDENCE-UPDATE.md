# Exact-message fee and native-balance integration — 26 October 2026

The cost calculator previously accepted every fee and funding figure from its
caller. This release adds a standalone reader/reviewer that binds a network fee
observation to exact unsigned message bytes and checks native funding against a
fresh system-account observation, after subtracting declared other reservations.

## Scope delivered

- Bounded legacy/v0 unsigned-envelope decoding, single fee payer, no address
  lookups, explicit CU-limit/price decoding and priority rounding.
- Up to five public read-only RPC calls with fixed endpoints, genesis checks
  before/after, finalized commitment, nondecreasing context slots, original
  timestamps, response limits and no retries, redirects or credentials.
- Raw fee versus caller cap checks, priority included exactly once, and exact
  native-balance arithmetic. Unknown reservations/costs stay unknown.
- Private exclusive report publication, sanitized provider failures, input and
  message/quote hashes, and replayable projected fee/native observations.
- Separate evidence and economic results. Route semantics, reservation authority,
  USDC principal balance and execution approval explicitly remain unverified.

The adapter accepts a validated cost *schema*, not an authenticated swap route.
The test fixture intentionally uses a non-swap instruction to demonstrate that
valid fee evidence must never be presented as swap approval. Devnet mode produces
fee evidence only; it never interprets devnet test assets as economic USDC.

## Validation and deployment

The execution-cost suite now contains 67 tests: 40 existing arithmetic/CLI tests
and 27 evidence integration tests. New coverage includes signed/malformed messages,
wrong payer, unsupported lookups, fee caps, priority consistency, altered quote
bindings, unknown reservations, balance shortfalls, exact large integers, clocks,
slot regression, genesis mismatch, null results, transport limits/errors and
exclusive CLI publication. All RPC observations in these tests are synthetic.
No actual host/live fee capture or performance claim follows from these tests.

No scanner, observer, polling rate, notification, statistics reader, model,
frozen-study registration, production database or completed devnet journal is
modified. No service is installed and no Kali restart is required. The CLI is
optional and performs reads only with `--allow-public-read`; it has no signer or
sender. It is not scheduled or imported by production.

Run the focused tests from the development checkout:

```bash
cd ~/apps/solana-radar-dev/execution-cost
python3 -E -s -m unittest discover -p 'test_*.py'
```

Do not prepare a live input by recycling old completed devnet transactions or
resetting their journals. A narrowly supported route adapter and fresh unsigned
messages are the next integration gate. Input schema and explicit read command
are documented in [execution-cost/README.md](../execution-cost/README.md).

## Roadmap checkpoint

Infrastructure and controlled devnet mechanics are established; execution cost
evidence is now a tested component. Mainnet route semantics, token spendability,
authoritative reservations and an integrated execution preflight remain unfinished.
The frozen study review remains October 28 at 17:30 Europe/Amsterdam. It can fail
or remain inconclusive. Neither this release nor a successful small execution
test would demonstrate a profitable trading strategy. See the current
[roadmap](ROADMAP.md) for the separate engineering and research gates.
