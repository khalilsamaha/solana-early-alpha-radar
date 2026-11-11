"""Research controller for a shared owner, run away from its dispatch loop.

Free subscriptions belong to the owner and are not misreported as research
sends. Cleanup is separately receipted by the owner, outside capture admission.
"""
import asyncio

from capture import canonical, strict_json


async def run(capture, lease, journal):
    pending = None
    subscribed = {}
    commands = 0
    outcome = "capture-stopped"
    cleanup = None

    async def send(method, keys):
        nonlocal commands
        if not capture.tick():
            return False
        if commands >= 1000:
            raise RuntimeError("shared-research-command-limit")
        payload = {"method": method, "keys": keys}
        intent = journal.intent(payload, capture)
        if not capture.tick():
            journal.abandon(intent)
            return False
        await asyncio.wait_for(lease.remote("send", canonical(payload)), 1)
        commands += 1
        journal.sent(intent)
        return capture.tick()

    try:
        journal.start(capture)
        if capture.state["messages"] or capture.state["gaps"]:
            raise RuntimeError("shared-fresh-session-required")
        while capture.tick():
            await lease.remote("heartbeat")
            expired = sorted(m for m, until in subscribed.items() if until <= capture.wall())
            if expired:
                if not await send("unsubscribeTokenTrade", expired):
                    break
                for mint in expired:
                    subscribed.pop(mint, None)
            if pending is None:
                pending = asyncio.create_task(lease.remote("recv"))
            try:
                raw = await asyncio.wait_for(asyncio.shield(pending), 0.05)
            except TimeoutError:
                continue
            pending = None
            stamp = journal.stamp()
            decision = capture.receive(raw)
            if decision == "watch-planned":
                journal.selected(capture, stamp)
            if capture.state["status"] != "active":
                break
            if decision == "watch-planned":
                mint = strict_json(raw)["mint"]
                if await send("subscribeTokenTrade", [mint]):
                    subscribed[mint] = capture.db.execute("SELECT until_ns FROM mints WHERE mint=?", (mint,)).fetchone()[0]
            elif decision in {"within-planned-watch", "outside-planned-watch"}:
                row = strict_json(raw)
                if row["txType"] in {"migration", "migrate"} and row["mint"] in subscribed:
                    if not await send("unsubscribeTokenTrade", [row["mint"]]):
                        break
                    subscribed.pop(row["mint"], None)
    except asyncio.CancelledError:
        outcome = "transport-cancelled"
        if capture.state["status"] == "active":
            capture.gap()
        raise
    except Exception:
        outcome = "transport-failed"
        if capture.state["status"] == "active":
            capture.gap()
    finally:
        if pending is not None:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        try:
            cleanup = await asyncio.wait_for(lease.remote("finish"), 2)
            if cleanup["outcome"] != "unsubscribed" or cleanup["reason"] != "research-stop":
                outcome = "transport-cleanup-failed" if cleanup["outcome"] != "unsubscribed" else "transport-failed"
        except BaseException:
            outcome = "transport-cleanup-failed"
        try:
            journal.finish(outcome, capture)
        except Exception:
            outcome = "measurement-failed"
    return {"outcome": outcome, "research_commands_sent": commands,
            "upstream_connections_opened_by_research": 0, "cleanup": cleanup,
            "receive_clock_scope": "capture-thread queue consumption; excludes upstream-to-queue delay",
            "local_send_clock_scope": "capture-thread receipt of upstream send completion",
            "provider_acknowledgement_verified": False, "billing_cutoff_verified": False}
