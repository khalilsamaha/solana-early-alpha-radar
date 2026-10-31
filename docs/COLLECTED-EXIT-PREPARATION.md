# Atomic collected exit preparation — 31 October 2026

The exit collector's 19-case Kali report was accepted at 06:05:55 UTC. This
increment connects that collector to the existing admission's durable exit record.
It is an internal integration with an offline-only host exercise, not a deployment
or a new controlled cycle.

## Collection and persistence

The collector now retains the final genesis response, in addition to checking it.
The private envelope contains initial deployment/pool evidence, fresh packet
construction, account/simulation evidence, request parameter hashes and clocks,
and the exact admission/accounting identity. Public output excludes raw wire and
provider evidence.

The coordinator closes read-only collection connections, reacquires the cooperating
wallet lock, and opens one SQLite transaction. It independently replays the raw
preparation and collection protocol. It checks the current admission identity,
STOP and the original deadline again. Preparation and collection are one immutable
record in the same ledger: either both commit, or neither does.

Replay checks the fixed twenty-request method/parameter sequence, finalized
contexts, devnet genesis responses, blockhash, exact-message fee, response clocks,
raw evidence hashes and entry-time ownership. Updating a checksum does not bypass
contradictory evidence. These records establish local provenance; they are not
cryptographic attestations by an RPC provider.

The collected record has a distinct format. Older raw preparations remain readable
and cannot be implicitly upgraded or replaced. Repeated coordination reopens an
existing record without new RPC. Expired records retain their original deadline;
a later STOP remains visible without erasing historical provenance.

The raw evidence and collection each have a twelve-MiB cap; the combined record
has a twenty-four-MiB plus metadata cap. The database's sixty-four-MiB ceiling is
checked before commit. Storage failure, STOP or expiry before commit rolls back
the complete write. A completed record remains historical evidence and must be
checked for freshness again by any future signing integration.

## Recovery and remaining gates

The existing combined private snapshot automatically preserves this single record.
Its isolated, stopped replay now validates the collection semantics through the
updated reader. Legacy snapshot manifests retain their previous shape. No cloud
transfer, active restore or private-key backup is added.

Restricted exit signing and durable send/recovery are next. Final exit receipts,
residual balances, failed-attempt accounting and allocation release remain after
that. This increment releases no funds, consumes no exit attempt and cannot sign
or send. Mainnet support, runtime integration and funded-pilot approval remain
outside this scope. Monitoring, sampling, notifications and the fixed study do not
change; future live timing has not been established by the synthetic exercise.

The Kali report captured October 31 at 17:39:33 UTC matched all 21 cases and
flags. The next [durable signing handoff](EXIT-SIGNING-HANDOFF.md) is implemented;
its host acceptance is pending.

## Kali acceptance

Fetch the pinned source supplied in chat, then run:

```bash
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/admission_exit_collection_cli.py" \
  --output "$PWD/radar-collected-exit-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, 21 cases. The CLI has no live action or wallet
input. It blocks sockets/signing, uses temporary ledgers and fake HTTP, and writes
an exclusive summary file with owner-only permissions. Upload only that `.json.gz` report.
No Docker rebuild, service restart or host configuration change is required.
