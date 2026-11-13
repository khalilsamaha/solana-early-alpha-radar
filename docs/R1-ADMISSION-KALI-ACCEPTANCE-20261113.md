# R1 admission/supervision Kali acceptance — 13 November 2026

Accept the bounded offline admission/supervision/recovery gate at producer
`685d6359551c2eb69f4ccb37c06bf6424176cedf`, tree
`b3011ada33b681ead8adcd5e73a4ce477cd71fdb`. This is the correct new batch, unlike
the previously uploaded byte-identical duplicate of the earlier session batch.

## Supplied evidence and independent review

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| acceptance(3).zip | 378742 | `aec6f7ad758c9b2c723c34945be09866ed4fbbb24322e2439e20f2194b3b28b9` |
| validation(20261113-092020).log | 2298 | `c04750be3e8decef6f4215237641f1437a176220e12eb455e44e14dde595a1b7` |
| report(20261113-092020).json | 22331 | `d6640631cc900fbc7534e0aabef75214c163313a717622d9da68c6ffe287b793` |

Report/log are byte-identical to their bundled members. The ZIP has exactly the
30 expected bounded regular mode-0600 uncompressed members. All **163 source
fingerprints** match the pinned implementation. Python 3.14.6/websockets 17.4 is
reported. All **15 named tests** passed, with zero failures/errors/skips and no
match for the diagnostic rejection pattern. Batch time: 21.922847 seconds; tests:
5.464 seconds. No unchanged session or Docker fixture suite was rerun in this review.

All five canonical request/claim/frozen-draft bindings were independently checked,
including exact proposal, source fingerprints/digest, fixture limits, resources,
request identity, parent binding and authority-denial fields. All terminal and
read-only recovery receipts match their expected schema and request identities.
Host filesystem paths inside those records were treated as data, not opened or
used as restore targets on the reviewing machine.

For normal, idle and cleanup-failure, all three worker receipts and exact archives
were independently verified, capture/journals replayed and evidence restored into
fresh isolated temporary directories. Actual Node discovery results and native
Unix peer claims match the intended scenario. Normal/idle remain capture-stopped;
cleanup-failure remains transport-cleanup-failed within complete evidence.

The stalled and diagnostic-tainted cases both reached their request-bound fault
markers. Their exact exit statuses are -14 (SIGALRM) and 1 respectively. Both
remain failed with reconciliation required, without completion receipts/archives.
No failed capture or worker is promoted to success by the overall checker pass.

Recorded session journal times are **13 November 2026,
09:40:03.251404–09:40:07.546054 CET** (08:40 UTC). These are host-reported artifact
timestamps, not an independently attested clock or the uploaded filename's time.
This review used supplied files; it did not access Kali, a provider, RPC or B2 live.

Accepted status: `admission-offline-passed-live-blocked`. No repeat batch is needed
without a material change or new failure. Production handoff, complete R1 approval,
provider activation, real credential provisioning, live retention and approved
measurement/exposure terms remain open. E0 is independent and held.

## Next connected engineering work

The next work is the bounded read-only production inventory and blocked handoff
prerequisite report, implemented in [r1-handoff-review](../r1-handoff-review/README.md).
It gathers identity/resource evidence needed for production binding while retaining
all unresolved ownership, connection-closure, rollback, live-policy, retention and
authority gates. It does not fabricate eight-step production lifecycle receipts or
change the accepted admission/session implementation.
