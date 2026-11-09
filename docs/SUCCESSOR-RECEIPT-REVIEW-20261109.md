# Successor receipt effects review

The successor transport's finalized state proves only that its bounded provider
capture names the exact signed generation with finalized status. It does not
validate full token/native effects, apply accounting or close the position.
Original-generation accounting cannot be reused unchanged: its one-attempt fee
partition would conflate the successor with the retired attempt's unresolved
fee exposure.

This increment adds a read-only internal reviewer. Under the existing source
lock and one read-only snapshot it replays source, retirement, successor,
signing, independent backend ACK and the authenticated transport event chain.
It builds the private intent from that successor's own capture and signed wire,
normalizes the stored raw receipt, and uses the existing exact-wire receipt
validator and admitted vault/authority checks. Capture finish times come from
the authenticated journal event envelope, not an imported report.

Only a complete finalized success or fee-only failure can yield observed effects.
The review checks exact owned spend, residual and protected inventory, minimum
output, unchanged account lifecycle, native fee/rent conservation and policy
caps. Conflicting or malformed effects cannot be usable. Review remains possible
after STOP/expiry without a private key; it never resumes an attempt.

The returned fee projection distinguishes known entry/successor fees from the
retired attempt's unresolved exposure. Journal holds remain unchanged. Neither
the projected fee deduction nor historical token effects are persisted, and
they confer no current wallet balance, closure, release or next-entry authority.
No existing lifecycle projection or original-generation accounting is modified.

The only CLI is an offline test runner using disposable keys and journals with
network connections blocked. It accepts only `--output`, refuses overwrite and
cannot import the prior observation as an execution or accounting instruction.

## Kali acceptance

Run `position-book/successor_receipt_review_cli.py --output NEW.json.gz` from the
pinned development commit using `python3 -B -E -s -W error::ResourceWarning`.
The six connected tests include successful and failed receipts, absent/partial
evidence, STOP/expiry, repeated review and byte preservation, wrong generations,
and rehashed fee, metadata, vault and protected-inventory tampering. They do not
contact the operational wallet or a real RPC endpoint.

Remaining E0 work includes a durable successor-specific accounting/closure
contract, fresh residual/protected balance checks, handling of the retired
attempt's unresolved exposure, and a separately scoped operational adapter with
complete collect/commit/sign/send timing. A passing observation does not measure
those later costs. Do not initiate an operational attempt on this increment.
Kali acceptance of this increment does not complete E0 or clear consolidation.
