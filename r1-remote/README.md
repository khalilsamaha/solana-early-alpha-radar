# Fixed synthetic package remote boundary

This increment adds a fixed B2 command adapter and durable finalization for only
three synthetic packages accepted from the November 12 delivery check. The
accepted report SHA-256 is
`f6ca0fcaadd391a4579e8b34eabd6e9259745940c1290d1f6156202efd00179f`.

| Package | Bytes | SHA-256 |
| --- | ---: | --- |
| normal | 125546 | `9492acc0b03653d1612304592fad470ecb9efb65c4a45f220ef139ef301988aa` |
| cleanup-failure | 125620 | `33c2291e227708a3db3edf104d1e5f28d423bc47058229e8106453138128c86c` |
| shutdown-interruption | 119856 | `d7a4ba524ab5fdb115a39cc5d9f7a5b72dcade24e5dae814f597446827b75795` |

Only `check_remote.py` is exposed as a CLI. It mocks every B2 command and the
credential-access boundary, denies Python network connections, and exercises
bounded local subprocess I/O using disposable Python children. It does not run
sudo/rclone, contact B2, access credentials, operate Docker or regenerate session
fixtures. Copying uploaded evidence privately for review does not alter originals.

The internal adapter keeps the existing root-owned executable checks, fixed
rclone configuration and `r1-rehearsal/` destination. Three ordered commands at
most: check backend, upload through stdin, download the exact generated object.
There is no alternate destination, delete, retry, sync, key or permission change.
It uses a 128 KiB transfer ceiling because these fixed packages exceed the older
64 KiB profile; the earlier runner and its accepted source pins are unchanged.
Download is limited to the exact expected size plus one byte. Stdout is drained
with an allocation cap while stdin is written, and every local subprocess is
reaped. The existing privileged timeout wrapper has a 40-second maximum with
two-second kill grace; outer timeout adds four seconds. Adapter budget is 135
seconds. These are transfer bounds, not capture/timing threshold changes.

The source package and acceptance report are frozen, fully restored and checked
before a durable intent is published and before credentials could be accessed.
Backend/upload/download uncertainty consumes that control directory and retains
the package and failure stage. Successful upload is not finalization. Completion
is published only after exact downloaded bytes, independent receipt/evidence
restore and final input/source checks. Interrupted evidence stays quarantined.
An incomplete or partially written completion is not acceptance: retain the
entire directory for manual review; no retry or automatic reconciliation CLI is
provided. This increment does not implement a remote recovery reader.

The offline check accepts the ORIGINAL delivery output directory (containing
all three `*-package.zip` files) and its ORIGINAL `report.json`. Do not regenerate
these inputs. Absolute, private, non-symlink paths are required. Use a new output
directory once; retain failure logs.

Expected result: `offline-remote-boundary-passed-b2-pending`, 18 tests with zero
failures/errors/skips, all three independent package restores. Upload its report
and validation log. This accepts the new boundary on Kali, not actual delivery.

Actual remote invocation remains unexposed pending this gate and concrete review
of the destination, retained-object reconciliation and transfer authority. The
previous accepted B2 session test must not be repeated. Existing B2 storage/API
accounting could apply to a later authorized transfer; no free-storage claim is
made. Successful round trip would still not establish retention duration, access
policy/encryption, scheduled live backup coverage or full R1 acceptance. No
provider activation, production rollout, wallet use, model fitting or extra
engineering effort cap follows from this work.
