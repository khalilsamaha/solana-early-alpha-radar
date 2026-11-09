# Offline successor completion rehearsal

This additive E0 rehearsal connects the existing real-clock, 1 MiB successor
collection/sign/send fixture to full receipt metadata, durable successor
accounting and finalized five-account balances. It exposes no operational mode.

The simulated sender loses its one response after the durable send boundary.
Recovery observes that exact signature after removal of the disposable key and
creation of the fixture STOP. The provider supplies complete raw transaction
metadata. Accounting applies once, even after STOP; a duplicate does not write.
Independent lifecycle and locked recovery projections must agree. The recovery
projection uses the existing binding operation owner and source/admission locks.

STOP must prevent balance requests. Only the STOP created inside this disposable
fixture is then removed. Four synthetic reads provide balances constructed from
the raw receipt's post-balance arrays and captured mint/account metadata, rather
than the accounting output being tested. Balance validation must finish with
positive headroom, including source replay and closing locks/connections.

The send deadline and balance freshness window are separate checks. No clock is
frozen, deadline widened, request retried, or failed report relabeled as a pass.
Reusable fixture history setup is unchanged; measured completion operations use
their normal operation scopes. Synthetic timing excludes real provider latency
and finality delay and cannot authorize an operational transaction.

The final checks compare every predecessor table, source file and original
signing marker. Only successor preparation, signing, transport and accounting
tables may have been added. Known paid fees plus remaining held fees must equal
the previous total; retired exposure must remain positive and covered. There is
exactly one synthetic send, no remaining disposable key, no scoped closure and
no funds available for a new entry.

## Kali acceptance

Run the pinned development version with:

```bash
python3 -B -E -s -W error::ResourceWarning position-book/successor_completion_cli.py --output NEW.json.gz
```

Expected: `offline-integration-passed`, 13 accounting checks (including receipt
validation), 9 balance checks and 12 connected checks. Both reported deadline
headrooms must be positive. The output path must be new; operational arguments
are unsupported. Upload failed reports as well as successful reports.

This accepts one offline integration increment only. It does not establish
operational receipts or balances, resolve retired exposure, close E0, authorize
execution, or clear a PR, CI run or merge. Full phase acceptance remains separate.
