"""Bounded local subscription evidence; no provider acknowledgement or billing claim."""
import os
from pathlib import Path
import time

import capture as c
from handoff import path_without_links, read_private
from rpc_probe import identifier

MAX_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 4096
MAX_RECORD_BYTES = 4096
OUTCOMES = {"capture-stopped", "transport-failed", "transport-cleanup-failed", "transport-cancelled"}


def command_valid(command):
    if not isinstance(command, dict):
        return False
    method = command.get("method")
    if method in {"subscribeNewToken", "subscribeMigration"}:
        return set(command) == {"method"}
    if method in {"subscribeTokenTrade", "unsubscribeTokenTrade"} and set(command) == {"method", "keys"}:
        keys = command["keys"]
        return (isinstance(keys, list) and 1 <= len(keys) <= 32
                and all(identifier(k, 32) for k in keys) and len(keys) == len(set(keys)))
    return False


def snapshot(capture):
    return {"rows": capture.state["rows"], "chain_sha256": capture.state["chain_sha"]}


class Journal:
    def __init__(self, path, *, wall=time.time_ns, monotonic=time.monotonic_ns):
        path = path_without_links(path)
        c.private_directory(path.parent)
        self.fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        self.wall, self.monotonic = wall, monotonic
        self.seq = self.size = 0
        self.chain = c.GENESIS
        self.last_mono = self.last_wall = -1
        self.pending = None
        self.finished = self.failed = False
        try:
            c.sync_dir(path.parent)
        except BaseException:
            self.close()
            raise

    def __repr__(self):
        return "<R1 local measurement journal>"

    def stamp(self):
        return {"received_wall_ns": self.wall(), "received_mono_ns": self.monotonic()}

    def _append(self, kind, payload):
        try:
            if self.fd is None or self.finished or self.failed:
                raise c.CaptureError("measurement-closed")
            wall, mono = self.wall(), self.monotonic()
            if (type(wall) is not int or type(mono) is not int
                    or wall < max(0, self.last_wall) or mono < max(0, self.last_mono)):
                raise c.CaptureError("measurement-clock")
            record = {"seq": self.seq + 1, "previous": self.chain, "kind": kind,
                      "wall_ns": wall, "mono_ns": mono, "payload": payload}
            hashed = c.digest(c.canonical(record).encode())
            raw = (c.canonical(dict(record, sha256=hashed)) + "\n").encode()
            if (len(raw) > MAX_RECORD_BYTES or self.seq >= MAX_RECORDS
                    or self.size + len(raw) > MAX_BYTES):
                raise c.CaptureError("measurement-limit")
            # A partial write/error is retained as incomplete evidence. Do not
            # emit further commands or try to repair/rewrite the journal.
            view = memoryview(raw)
            while view:
                count = os.write(self.fd, view)
                if count <= 0:
                    raise c.CaptureError("measurement-write")
                view = view[count:]
            os.fsync(self.fd)
            self.seq, self.chain, self.size = record["seq"], hashed, self.size + len(raw)
            self.last_wall, self.last_mono = wall, mono
            return self.seq
        except BaseException:
            self.failed = True
            raise c.CaptureError("measurement-write-failed") from None

    def start(self, capture):
        if self.seq:
            raise c.CaptureError("measurement-already-started")
        self._append("start", {"capture_start_ns": capture.state["start_ns"],
                               "limits": capture.state["limits"]})

    def selected(self, capture, stamp):
        row = capture.db.execute("SELECT raw FROM events WHERE seq=?", (capture.state["rows"],)).fetchone()
        mint = c.strict_json(row[0])["mint"]
        self._append("selected", dict(snapshot(capture), mint=mint, **stamp))

    def intent(self, command, capture):
        if self.pending is not None or not command_valid(command):
            raise c.CaptureError("measurement-command")
        self.pending = self._append("intent", dict(snapshot(capture), command=command))
        return self.pending

    def sent(self, intent):
        if self.pending != intent or self.pending is None:
            raise c.CaptureError("measurement-intent")
        self._append("sent", {"intent_seq": intent})
        self.pending = None

    def abandon(self, intent):
        if self.pending != intent or self.pending is None:
            raise c.CaptureError("measurement-intent")
        self._append("abandoned", {"intent_seq": intent, "reason": "capture-limit"})
        self.pending = None

    def finish(self, outcome, capture):
        if outcome not in OUTCOMES:
            raise c.CaptureError("measurement-outcome")
        self._append("finish", dict(snapshot(capture), outcome=outcome,
                    messages=capture.state["messages"], gaps=capture.state["gaps"],
                    stop_reason=capture.state["reason"]))
        self.finished = True

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def replay(capture_path, journal_path):
    """Replay a complete journal against a closed, independently verified DB."""
    raw = read_private(journal_path, MAX_BYTES)
    if not raw.endswith(b"\n") or len(raw.splitlines()) > MAX_RECORDS:
        raise c.CaptureError("measurement-incomplete")
    with c.checked(Path(capture_path)) as (db, state):
        events = {seq: (chain, kind, decision, c.strict_json(data)["mint"]) for seq, chain, kind, decision, data
                  in db.execute("SELECT seq,chain_sha,kind,decision,raw FROM events")}
        selected_expected = {seq: row[3] for seq, row in events.items() if row[2] == "watch-planned"}
        observed, intents, completed, delays = {}, {}, set(), []
        pending = None
        abandoned = set()
        last = c.GENESIS
        last_mono = last_wall = -1
        final = None
        last_rows = 0
        lines = raw.splitlines()
        for seq, line in enumerate(lines, 1):
            if len(line) + 1 > MAX_RECORD_BYTES:
                raise c.CaptureError("measurement-record-limit")
            record = c.strict_json(line)
            if set(record) != {"seq", "previous", "kind", "wall_ns", "mono_ns", "payload", "sha256"}:
                raise c.CaptureError("measurement-schema")
            sha = record.pop("sha256")
            if (type(record["seq"]) is not int or record["seq"] != seq
                    or record["previous"] != last or c.digest(c.canonical(record).encode()) != sha
                    or type(record["wall_ns"]) is not int or type(record["mono_ns"]) is not int
                    or record["wall_ns"] < max(0, last_wall) or record["mono_ns"] < max(0, last_mono)
                    or not isinstance(record["payload"], dict)):
                raise c.CaptureError("measurement-integrity")
            p, kind, mono = record["payload"], record["kind"], record["mono_ns"]
            if seq == 1:
                if kind != "start" or p != {"capture_start_ns": state["start_ns"], "limits": state["limits"]}:
                    raise c.CaptureError("measurement-binding")
            elif kind in {"selected", "intent", "finish"}:
                rows = p.get("rows")
                if (type(rows) is not int or not last_rows <= rows <= state["rows"]
                        or p.get("chain_sha256") != (events[rows][0] if rows else c.GENESIS)):
                    raise c.CaptureError("measurement-row-binding")
                last_rows = rows
                if kind == "selected":
                    if (set(p) != {"rows", "chain_sha256", "mint", "received_wall_ns", "received_mono_ns"}
                            or pending is not None or rows in observed or selected_expected.get(rows) != p["mint"]
                            or type(p["received_mono_ns"]) is not int or type(p["received_wall_ns"]) is not int
                            or not max(0, last_mono) <= p["received_mono_ns"] <= mono
                            or not max(0, last_wall) <= p["received_wall_ns"] <= record["wall_ns"]):
                        raise c.CaptureError("measurement-selection")
                    observed[rows] = p
                elif kind == "intent":
                    if (set(p) != {"rows", "chain_sha256", "command"}
                            or pending is not None or len(intents) >= 1024 or not command_valid(p["command"])):
                        raise c.CaptureError("measurement-intent")
                    if p["command"]["method"] == "subscribeTokenTrade":
                        if (len(p["command"]["keys"]) != 1 or rows not in observed
                                or p["command"]["keys"] != [observed[rows]["mint"]]
                                or any(x["command"] == p["command"] for x in intents.values())):
                            raise c.CaptureError("measurement-subscribe-binding")
                    intents[seq], pending = p, seq
                else:
                    if (seq != len(lines) or set(p) != {"rows", "chain_sha256", "outcome", "messages", "gaps", "stop_reason"}
                            or p["outcome"] not in OUTCOMES or rows != state["rows"]
                            or pending is not None and p["outcome"] == "capture-stopped"
                            or type(p["messages"]) is not int or p["messages"] != state["messages"]
                            or type(p["gaps"]) is not int or p["gaps"] != state["gaps"]
                            or p["stop_reason"] != state["reason"]):
                        raise c.CaptureError("measurement-terminal-binding")
                    final = p
            elif kind in {"sent", "abandoned"}:
                expected_keys = {"intent_seq"} if kind == "sent" else {"intent_seq", "reason"}
                if (set(p) != expected_keys
                        or kind == "abandoned" and p.get("reason") != "capture-limit"
                        or type(p["intent_seq"]) is not int
                        or pending is None or p["intent_seq"] != pending):
                    raise c.CaptureError("measurement-completion")
                if kind == "sent":
                    completed.add(pending)
                    intent = intents[pending]
                    if intent["command"]["method"] == "subscribeTokenTrade":
                        delays.append(mono - observed[intent["rows"]]["received_mono_ns"])
                else:
                    abandoned.add(pending)
                pending = None
            else:
                raise c.CaptureError("measurement-sequence")
            last, last_mono, last_wall = sha, mono, record["wall_ns"]
        if final is None or set(observed) != set(selected_expected):
            raise c.CaptureError("measurement-incomplete")
        decisions = dict(db.execute("SELECT decision,count(*) FROM mints GROUP BY decision"))
        return {"status": "local-measurement-replayed-live-blocked", "journal_sha256": c.digest(raw),
                "journal_bytes": len(raw), "journal_records": len(lines), "capture_chain_sha256": state["chain_sha"],
                "session_outcome": final["outcome"], "messages_counted": state["messages"], "raw_rows": state["rows"],
                "creation_records_observed": sum(e[1] == "create" for e in events.values()),
                "unique_creation_mints_observed": sum(decisions.values()), "mint_decisions": decisions,
                "selected_creations": len(observed), "send_intents": len(intents),
                "local_sends_completed": len(completed), "send_intents_abandoned": len(abandoned),
                "send_intents_without_completion_or_abandonment": len(intents) - len(completed) - len(abandoned),
                "selected_without_completed_subscription_send": len(observed) - len(delays),
                "creation_receive_to_local_send_return_ns": {"count": len(delays),
                    "min": min(delays) if delays else None, "max": max(delays) if delays else None,
                    "sum": sum(delays)}, "gaps": state["gaps"], "stop_reason": state["reason"],
                "provider_acknowledged_subscriptions": None, "external_creation_denominator": None,
                "initial_trade_coverage": None, "billed_events": None, "data_fees_lamports": None,
                "ledger_order_verified": False, "finality_verified": False, "profitability_evaluated": False}
