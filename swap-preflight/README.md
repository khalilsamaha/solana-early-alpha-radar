# Combined devnet preflight

Read-only integration of the unsigned instruction contract, raw pool/account reader and full program deployment fingerprint. This component does not authorize signing or trading.

## Evidence boundary

The fixed baseline in `baseline.py` is the reviewed public observation from 19 October 2026 at slot 512857731. It pins program address, ProgramData pointer, deployment slot, upgrade authority, payload/header hashes and account lengths. It does not establish equivalence to published source, program safety, immutable deployment or independent consensus. The deployment has an upgrade authority. A changed deployment stops review; there is no automatic baseline replacement or CLI override.

Pool mode makes at most six public devnet RPC requests. Packet mode makes at most eight. Both use one finalized `getMultipleAccounts` batch containing the pool, configuration, mints, vaults, observation, executable program and full ProgramData. Packet mode adds wallet and both token accounts to this same batch. The same raw batch feeds both existing auditors; independently supplied pass reports are ignored.

Accounts must have arrived at most ten seconds before review. Their receipt time is recorded separately from capture completion, so later requests cannot refresh old evidence. Packet mode additionally checks the original unsigned policy deadline, blockhash validity and exact-message fee. It never replaces an expired policy or blockhash. Requests are bounded, without retries, proxies or redirects. Local clocks and one RPC provider remain trust assumptions.

## Modes

- No mode argument: fifteen synthetic offline checks, using a clearly labelled synthetic baseline.
- `--pool ADDRESS`: public devnet capture; success is `pinned-pool-snapshot`. Wallet balances and fees have **not** been checked.
- `--packet FILE`: current public unsigned contract packet; success is `preflight-evidence-consistent`. This is not a signing grant.
- `--input FILE`: offline replay of raw capture or this tool's report at its original capture time. `replayOnly=true`; no network requests. A saved pass is not current evidence or authorization.
- `--output FILE`: required, exclusive new report, private permissions, optionally gzip. Inputs and outputs have an 8 MiB decompressed cap.

All paths keep signing/execution approval false and make zero signatures, sends or position-book changes. No simulation is performed. Mint authorities remain explicit risk observations. Packet-mode integration is tested synthetically; a real current wallet-bound packet is a later host gate.

## Host check

From the live project directory, using the pinned development checkout supplied in chat:

```bash
umask 077
radar_stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
python3 -E -s "$HOME/apps/solana-radar-dev/swap-preflight/preflight_cli.py"   --output "$PWD/radar-preflight-check-$radar_stamp.json.gz"
python3 -E -s "$HOME/apps/solana-radar-dev/swap-preflight/preflight_cli.py"   --pool 3CxsELVbhg3L37ptLm7aihdWoSohUFnJxE3JxdCURFce   --output "$PWD/radar-preflight-capture-$radar_stamp.json.gz"
```

Upload both public reports, including any unavailable/mismatch result. Do not replace the baseline or rerun to select a passing sample. No rebuild, restart, wallet funding, private key access or cloud-backup operation is needed.

## Validation and next integration

Run `python3 -m unittest discover -s swap-preflight -p 'test_*.py'` in an isolated Python process, or `bash scripts/check.sh` for the full suite. Tests cover raw batch binding, deployment drift, stale evidence, original deadlines, exact fees, insufficient balances, transport limits and report replay.

The next development boundary is a purpose-restricted devnet swap flow connecting fresh preflight to signed simulation, a durable one-send journal and exact receipt/position accounting. The existing lifecycle signer is not an arbitrary swap signer and must not be widened implicitly. Real-money execution and strategy readiness remain separate unresolved gates.

Official RPC references:
- https://solana.com/docs/rpc/http/getmultipleaccounts
- https://solana.com/docs/rpc/http/isblockhashvalid
- https://solana.com/docs/rpc/http/getfeeformessage
