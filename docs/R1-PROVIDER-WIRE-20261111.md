# R1 provider wire — offline scope accepted on Kali

Date: 2026-11-11. The synthetic B2 round trip at `904a805` is accepted on Kali
and its downloaded package has been independently restored. This increment
implements the WebSocket wire used by the existing subscription controller.
It does not supply a live launcher, read a credential file or alter the scanner.

## Dependency decision

Use exactly **websockets 17.4**, released October 30, 2026. The official
[release](https://github.com/python-websockets/websockets/releases/tag/17.4)
resolves to commit `625a59ed613ac60e60d577dd64b8641d59ecb2b1`.
The [changelog](https://websockets.readthedocs.io/en/stable/project/changelog.html)
documents the fragmented-message memory-exhaustion fix in this release.
The runtime rejects other version strings; it does not silently fall back to
the development environment's preinstalled 16.0.

`requirements-wire.txt` selects the portable `py3-none-any` wheel directly,
with SHA-256 `c6bd2c9781915592b209160d0f017d4c7c82ad53075e6b0c24d2a89299e7f9e9`.
The downloaded bytes matched the digest in
[PyPI release metadata](https://pypi.org/pypi/websockets/17.4/json).
Tests used that portable wheel in an isolated virtual environment. No system
Python installation is modified and no unpinned dependency resolution is needed.
Kali uses the same wheel and the requirements file's mandatory hash check.

Relevant API behavior was checked in the installed 17.4 source and the official
[asyncio client documentation](https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html).
The implementation depends on the pinned redirect hook and asyncio transport
abort interface. Future upgrades require revalidation, not a version-range bump.

## Wire behavior and limits

`provider_factory(secret)` validates an in-memory credential and returns a
factory without performing I/O. Calling that factory attempts one connection
to the fixed `wss://pumpportal.fun/api/data` endpoint with a percent-encoded API
key. The factory refuses a second attempt even after failure. This is a per-
factory guarantee, not a machine-wide connection lock or authorization check.
No CLI, environment key reader or wallet-file interface is included here.

The connection requires TLS certificate verification and hostname checking.
Proxy inheritance, HTTP redirects and compression are disabled; a private
disabled logger prevents URI/handshake debug output. Connection failures return
fixed error codes. The library cannot send a trading HTTP request or a signed
transaction. Outgoing JSON permits only new-token/migration subscriptions and
selected-token subscribe/unsubscribe commands with valid, unique 32-byte mint
identifiers. Commands are capped at 4,096 bytes, 32 keys and 1,024 attempts.
The controller retains its pacing, sampling and capture-budget decisions.

Receive settings cap message bytes at 65,536, frame queue high/low watermarks
at 2/1, and write buffering at 4,096 bytes. The wire consumes streaming fragments
with its own 64-fragment and 65,536-byte assembly limits. After the first fragment,
completion must occur within two seconds. Raw/URL-encoded/JSON-escaped credential
variants are rejected before returning message bytes to the capture. These are
application bounds, not a measured total-process RSS guarantee.

One receive task is retained across the controller's short polling timeouts.
Cancellation of a poll therefore cannot restart a partially consumed message
or duplicate its first fragment. A stalled/oversized/malformed receive aborts
the connection. Session stop cancels/collects the receive task and aborts the
transport before waiting for closure. Provider disconnects become explicit
capture gaps; there is no automatic reconnection or claim of recovered history.
Ping/pong control frames are handled by the protocol, not counted as trade data.

The async connection/open/close timeouts bound the awaited operations. They are
not a whole-process deadline: OS DNS work may outlive cancellation. A guarded
launcher still needs process/resource limits, private credential loading,
single-owner coordination, budget approval and preservation integration before
live use. Closing a local socket does not prove a hard provider billing cutoff.

## Offline validation scope

The tests exercise the actual 17.4 client and server handshake/framing codecs
over an in-memory asyncio transport. A local Unix listening-socket attempt was
unavailable in this execution environment; the final harness does not require
listening sockets or elevated access. It replaces only the byte transport,
while keeping the client handshake, redirect handling, masked commands,
fragment assembly, control frames and capture controller in the exercised path.

Tests cover fixed endpoint/TLS settings, exact dependency rejection, no-I/O
factory creation, no retry after failure, disabled logs and sanitized errors,
outgoing command restrictions, cancellation during send, secret/byte/fragment
bounds, fragment stalls, silent-reader cleanup, fragmented-message polling,
ping/pong, oversized messages, fragment floods, rejected redirects, stopping at
the capture limit, and disconnect gap recording without provider-reason leakage.

The runner now installs an audit hook blocking Python DNS operations and
IPv4/IPv6 socket creation/connect/sendto. A direct regression checks that block.
The report records dependency version, source hashes and these explicit limits:
`protocol_peer: in-memory`, `provider_connection_opened: false`,
`tls_handshake_tested: false`, `coexistence_accepted: false`.
This is not evidence of live endpoint availability, certificate-chain success,
provider billing, subscription acknowledgements or real feed coverage.

Development validation: **227 tests passed**, zero failures/errors/skips,
including 16 new wire/protocol tests and one runner network-guard test. The final
run used Python 3.12.14, SQLite 3.53.1 and the portable websockets 17.4 wheel,
with ResourceWarning treated as an error. It completed in 1.355153 seconds
and pins 30 source files. A separate `pip download --require-hashes` verification
also accepted the exact requirements file and wheel digest.

## Connection-policy decision — single shared socket selected

The owner supplied single-connection guidance on November 11. The project now
selects **one authenticated upstream connection**, multiplexing free creation/
migration and selected token trades. The earlier request for a two-socket
coexistence clarification is superseded. Do not run this wire alongside the
existing scanner's independent socket.

Official [real-time documentation](https://pumpportal.fun/data-api/real-time/)
and [FAQ](https://pumpportal.fun/FAQ/) were rechecked. They support the selected
multiplexing pattern. The supplied summary's IP-level enforcement claim is not
explicit in those pages; it is not recorded as an independently verified support
reply. No further clarification is needed to adopt the conservative single-socket
design, and no provider message or connection was sent by this work.

The existing controller aborts its wire on terminal limits. Simply sharing that
wire would stop discovery. Replacing abort with a no-op would risk retaining
paid subscriptions. The connection owner, research shutdown and local scanner
interface must therefore be implemented and tested together, as specified in
`R1-LIVE-READINESS-20261111.md`.

The choice is accepted as an engineering constraint, not a live-launch approval.
Existing scanner operation remains unchanged pending implementation, Kali
validation and a reviewed rollout. The original five-working-day effort cap
continues without extension.

## Kali acceptance and continuation

The uploaded 227-test report for `a2fdf580` passed review on 2026-11-11.
All 30 source hashes matched. Python 3.14.6 / SQLite 3.53.4 / websockets 17.4;
3.492902 seconds; zero failures/errors/skips. Report SHA-256:
`843e1a65b370a23b0eacd5ed26d2955538adf859390796e60f2d9a338ab5023b`.
This accepts the offline scope only. The next increment is documented in
`R1-SUPERVISOR-20261111.md`; do not repeat this earlier wire-only check.

The following records the completed wire-only action:


Fetch the new pinned commit/tree into an independent review directory, create
its virtual environment, install the exact wheel with `--require-hashes`, then
run `r1-data/check.py` with that interpreter. Upload its single report. Expected:
227 tests and `offline-provider-wire-passed-live-blocked`. No API key, sudo,
funding, cloud round-trip repeat or production restart is needed.

After Kali acceptance, implement the selected shared connection and guarded launcher,
then actual host TLS/session validation under the accepted connection model.
Live-capture preservation/retention and the fixed measurement contract must be
ready before the owner's numeric funding decision. Full R1 remains open;
there is no PR/CI consolidation, merge, paid activation or ML fitting here.
