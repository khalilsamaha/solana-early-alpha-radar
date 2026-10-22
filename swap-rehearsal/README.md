# Restricted devnet swap signing and simulation

This release connects the unsigned swap contract and fresh combined preflight to a separate, one-shot local signer and signed simulation. It does not implement transaction submission or connect the position book. Scanner, signal rules, quote collection, backups and existing self-transfer/WSOL signers remain unchanged.

## What was verified before this release

The host preflight at 19 October 2026 19:52:31 UTC exactly replayed as `pinned-pool-snapshot` at slot **512909802**. All six public reads returned. Program deployment identity matched the reviewed observation and the fifteen-case self-check matched exactly. Both pool token mints retained mint authorities. This pool-only report did not check wallet token accounts, fees or a swap packet. PR #34 CI passed.

## New signing boundary

`rehearsal_cli.py --action prepare` requires a dedicated existing devnet wallet directory, explicit public wallet, separately supplied scope file, a current unsigned packet, and `--allow-devnet-sign`. The scope must bind exactly the accounts, input/minimum output and caps in the packet. It is caller-supplied policy, not an independently authenticated trading decision. No scope is automatically inferred by the CLI.

Hard limits: legacy message only; exactly one signer, fourteen static keys and three instructions (compute unit limit, compute price, fixed devnet CPMM `swap_base_input`). Standard existing SPL accounts only, no native/WSOL mint, ALT, account creation/closure or arbitrary instructions. Maximum input is **1,000 atomic token units**, maximum total fee **10,000 test lamports**, maximum 300,000 compute units, price at most 10,000 micro-lamports/CU and priority fee cap at most 3,000 test lamports. Atomic units are not dollars or a quote valuation.

The controller obtains a fresh eight-request preflight itself; uploaded captures cannot authorize signing. It records the scope and packet before preflight, saves raw preflight privately, checks freshness again, then writes an exact signing request. The separate Node signer independently reconstructs the full canonical message and compares bytes, wallet identity, scope, fee assertion, deadlines and fixed caps. It also checks hashes binding the request to its recorded plan and capture. These checks complement the controller's raw program/account audit; the signer does not independently query the chain.

An exclusive, fsynced `signing-attempt.json` is created **before** signing. The signed wire is saved privately before simulation. A repeated prepare invocation, crash, timeout, expired packet or incomplete attempt cannot silently produce another signature. No automatic reset, replacement or resimulation exists. An interrupted attempt may have created a signature even if its result was not saved; that remains explicitly unknown.

All new files are under `swap-simulation-v1` in the existing private rehearsal directory; existing state is preserved. A persistent `STOP` marker blocks progression. The existing session lock excludes simultaneous rehearsals. This is local same-user process isolation, not a hardware security boundary: an owner deleting/copying state or altering code is outside the guard. Signed simulation bytes could be submitted by a holder or RPC provider while valid; the tool itself has no send method and does not export signed wire in public reports.

## Simulation evidence

Uses the original blockhash with `sigVerify=true`, `replaceRecentBlockhash=false`, finalized commitment and a minimum context slot. A successful status alone is insufficient: checks exact signed identity, fee and compute limit, full native balance delta vector, four SPL token pre/post rows, five returned account snapshots, unchanged account authorities/layout/rent, exact input debit and vault credit, minimum output and corresponding vault debit. Missing token evidence or a changed wallet prebalance stops the rehearsal. Concurrent vault amount changes between preflight and simulation are permitted only when the simulation's own token flow and returned snapshots reconcile.

Simulation is followed by a devnet genesis check. The complete preparation uses at most eight preflight requests plus two simulation/identity requests, without retries. A later program upgrade is still possible. Program fingerprint matching is not source/build equivalence or program safety, and simulation is not execution or profitability evidence. Durable receipt accounting and position integration remain pending.

## Host actions for this release

1. Run the default self-check. It creates temporary **unfunded disposable keys**, exercises real local signature generation against synthetic transport, checks twelve cases, and removes temporary files. It never opens your existing wallet and makes zero public RPC requests.
2. Run `--action inventory` with the reviewed pool capture and your public devnet wallet. Five read-only public requests check devnet identity, native balance and existing token accounts for the two pool mints. This mode does not read any private key or wallet directory, create accounts, request an airdrop, acquire tokens or sign anything.

The inventory uses the old capture only for reviewed pool/mint identity and labels it historical. Current inventory requests have increasing minimum context slots but are not one atomic signing snapshot. Supported accounts and balances are reported without automatic selection. An empty list is a useful result: it identifies a missing prerequisite. Do not buy tokens for this test. The next engineering decision is how to provision an isolated devnet token test setup, if necessary.

Exact checkout and commands are supplied in chat. Upload the two public `.json.gz` reports. No rebuild/restart or overnight waiting is required. Keep private rehearsal files local.

## Developer interface

`prepare` is implemented and covered by synthetic integration tests, but is not the host action requested in this release. A live current packet producer, explicitly reviewed scope and suitable devnet token balances are prerequisites. It will refuse expired packets and never regenerate them. `--action status --directory ... --wallet ... --output ...` reads existing durable state with zero RPC requests and no signing. Do not delete a failed attempt to retry.

Run `bash scripts/check.sh` for the isolated regression suites. Run the new suite alone with `(cd swap-rehearsal && python3 -m unittest discover -p 'test_*.py')`.

Official RPC references:
- https://solana.com/docs/rpc/http/simulatetransaction
- https://solana.com/docs/rpc/http/gettokenaccountsbyowner
