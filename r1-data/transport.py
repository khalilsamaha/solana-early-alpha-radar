"""Single-session subscription controller, tested with an injected offline wire.

This module neither constructs a network client nor loads credentials. A real
adapter and launch authorization remain separate prerequisites. An injected
wire must provide async send(str), recv(), close() and synchronous abort().
"""
import asyncio

from capture import CaptureError, canonical, strict_json


async def run_session(capture, wire_factory, *, poll_seconds=0.25, send_seconds=1.0, journal=None):
    """Never reconnect. Terminate on gaps, capture limits or transport failure."""
    if not (0.01 <= poll_seconds <= 1 and 0.01 <= send_seconds <= 2):
        raise CaptureError("invalid-transport-timeouts")
    commands = 0
    wire = None
    subscribed = {}
    outcome = "capture-stopped"

    async def send(method, keys=None):
        nonlocal commands
        if not capture.tick():
            return False
        # All sends originate here; no arbitrary method or destination input.
        if method not in {"subscribeNewToken", "subscribeMigration",
                          "subscribeTokenTrade", "unsubscribeTokenTrade"}:
            raise CaptureError("invalid-method")
        if commands >= 1024:
            raise CaptureError("command-limit")
        payload = {"method": method}
        if keys is not None:
            payload["keys"] = keys
        intent = journal.intent(payload, capture) if journal is not None else None
        if journal is not None and not capture.tick():
            journal.abandon(intent)
            return False  # durable logging must not let a stale deadline authorize a send
        await asyncio.wait_for(wire.send(canonical(payload)), send_seconds)
        commands += 1
        if journal is not None:
            journal.sent(intent)
        # Conservative ceiling below the documented 200 messages/second. The
        # final network adapter must also enforce bounded connection/close I/O.
        await asyncio.sleep(0.01)
        return capture.tick()

    try:
        if journal is not None:
            journal.start(capture)
        ready = capture.tick()
        if ready:
            if capture.state["messages"] or capture.state["gaps"]:
                raise CaptureError("fresh-session-required")
            wire = await asyncio.wait_for(wire_factory(), 5.0)
            ready = await send("subscribeNewToken") and await send("subscribeMigration")
        while ready and capture.tick():
            now = capture.wall()
            expired = sorted(m for m, until in subscribed.items() if until <= now)
            if expired:
                if not await send("unsubscribeTokenTrade", expired):
                    break
                for mint in expired:
                    subscribed.pop(mint, None)
            try:
                raw = await asyncio.wait_for(wire.recv(), poll_seconds)
            except TimeoutError:
                continue  # next tick enforces the original deadline during silence
            if isinstance(raw, str):
                raw = raw.encode("utf-8")
            received = journal.stamp() if journal is not None else None
            decision = capture.receive(raw)
            if journal is not None and decision == "watch-planned":
                journal.selected(capture, received)
            if capture.state["status"] != "active":
                break  # close instead of subscribing after the final allowed frame
            if decision == "watch-planned":
                row = strict_json(raw)
                if await send("subscribeTokenTrade", [row["mint"]]):
                    subscribed[row["mint"]] = capture.db.execute(
                        "SELECT until_ns FROM mints WHERE mint=?", (row["mint"],)).fetchone()[0]
            elif decision in {"within-planned-watch", "outside-planned-watch"}:
                row = strict_json(raw)
                mint = row["mint"]
                if row["txType"] in {"migration", "migrate"} and mint in subscribed:
                    if not await send("unsubscribeTokenTrade", [mint]):
                        break
                    subscribed.pop(mint, None)
    except asyncio.CancelledError:
        outcome = "transport-cancelled"
        if capture.state["status"] == "active":
            capture.gap()
        raise
    except Exception:
        outcome = "transport-failed"
        if capture.state["status"] == "active":
            capture.gap()
        # Never return the provider exception, URL, wire repr or credentials.
    finally:
        if wire is not None:
            # Abort first: do not continue receiving billable data during a
            # graceful close handshake. This still cannot enforce provider billing.
            try:
                wire.abort()
            except Exception:
                outcome = "transport-cleanup-failed"
            try:
                await asyncio.wait_for(wire.close(), 1.0)
            except Exception:
                outcome = "transport-cleanup-failed"
        if journal is not None:
            try:
                journal.finish(outcome, capture)
            except Exception:
                outcome = "measurement-failed"
    return {"outcome": outcome, "commands_sent": commands,
            "connections_opened": int(wire is not None),
            "subscription_acknowledged": False, "provider_billing_verified": False}
