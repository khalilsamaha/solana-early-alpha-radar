# Controlled test-pool swap simulation — 21 October 2026

## Evidence accepted

The 20 October 21:47 UTC host pool report records one submission and finalized success for pool `EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT`. Independent review reconstructed the deterministic addresses, message, Ed25519 wallet signature and full wire hash. Raw post-account evidence agrees with 500 tokens per vault, 500 per remaining wallet holder, and LP accounting. The 180,774,560-lamport debit reconciles to creation fee, account rent and transaction fee. The full raw transaction receipt is not exported; complete receipt validation was performed on the host. The separate 70-case host self-check matched the source.

Pool creation is complete. Do not repeat it or remove the private setup journals.

## This release

`devnet-pool/swap_cli.py` connects the finalized local token-pair/pool journals to the existing fresh-packet builder and restricted signed-simulation workflow. It requires both the explicit wallet and pool address. It revalidates signed setup messages, receipt identity and accounting, slot ordering and raw account effects before deriving the fixed scope. Historical setup evidence is labelled as historical; the existing controller still obtains a fresh combined pool/program/wallet snapshot and checks the current deployment fingerprint, blockhash validity and exact message fee before signing.

The test scope is fixed, not selected from a route response:

| Property | Value |
| --- | --- |
| Direction | Raw-byte-sorted mint0 to mint1 |
| Input | 1,000 atomic units = 0.001 six-decimal test token |
| Minimum output | 990 atomic units = 0.000990 test token |
| Priority fee | Zero |
| Total message fee cap | 10,000 devnet lamports |
| Compute unit cap | 300,000 |
| Transaction | Existing standard SPL accounts, fixed devnet CPMM swap |

Minimum output is a deliberate test constraint, not an executable price estimate or a profitability claim. If current fees/reserves cannot meet it, simulation must fail. No automatic relaxation exists.

The full path has at most 14 public RPC requests: four for the fresh packet, eight for preflight, and two for signed simulation/cluster confirmation. It makes no sendTransaction request. Original 15-second packet and 10-second evidence deadlines remain enforced. Simulation uses signature verification, the original blockhash, exact native/SPL delta checks and returned account reconciliation. There is no mainnet path, production integration or position-book update in this release.

Inspection and status make zero network requests. They use the existing Session to verify dedicated wallet identity, so they access the local key through the public-key reader but do not create a signature. Public reports exclude private key material and signed wire.

## Host sequence

Fetch the pinned release commit supplied in chat into `~/apps/solana-radar-dev`. There is no Docker rebuild or service restart.

1. Run the default `swap_cli.py --output ...` self-check: 17 offline cases with temporary unfunded wallets and synthetic transport. These exercise the actual serializers, collectors, signer and simulation reader, including large legacy program journals.
2. Run `--action inspect --directory ... --wallet ... --pool ... --output ...`. Expected state is `controlled-scope-ready`. This is a local historical-evidence review, not fresh chain authorization.
3. Run `--action simulate` with the same arguments plus `--allow-devnet-sign`. Expected success is `signed-simulation-consistent`; input is 1000 and simulated output must be at least 990 atomic units. Upload the public reports.
4. If interrupted or unsuccessful, use `--action status --directory ... --wallet ... --output ...`. Do not repeat simulate as a retry. An existing `swap-simulation-v1` journal is never reset, refreshed or overwritten. A different existing scope blocks the adapter. Status remains available for an incomplete journal.

No paid service, additional airdrop, pool creation or token purchase is needed for this phase. The software signer is a same-user process boundary rather than an OS sandbox or hardware wallet. Signed bytes remain private but could be submitted by a holder while valid, even though this tool has no broadcaster.

## Failure and recovery checks

New tests cover setup finality and receipt binding, raw account tampering, wallet/pool mismatch, program drift, holder-authority drift, expired blockhash, STOP, different or empty existing journals, inconsistent simulation balances, and interrupted signing. A lost acknowledgement after `signed.json` was durably saved now correctly reports one signature created in that run. An attempt marker without a signed result remains unknown, never zero and never automatically retried.

## Next gate

Review the host's actual signed simulation. Only then connect a separately tested one-send devnet swap submission and read-only recovery path, followed by reverse-swap and position accounting. Engineering rehearsal does not establish a profitable strategy; forward research qualification remains separate. Scanner, signals, quote budgets, ML and backups are unchanged.
