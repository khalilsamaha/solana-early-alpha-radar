"""Offline R1 capture core. No networking, key loading, signing or trading.

Receive order is evidence, never asserted to be ledger order. Sampling decisions
are plans for a future transport; they do not prove a subscription was installed.
"""
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
from urllib.parse import quote

VERSION = 1
MAX_DB = 32 * 1024 * 1024
MAX_EVENTS = 20_000
MAX_FRAME = 65_536
GENESIS = "0" * 64
BASE58 = re.compile(r"[1-9A-HJ-NP-Za-km-z]+\Z")


class CaptureError(Exception):
    """Only constant, non-sensitive codes cross the public error boundary."""


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def chain(previous, seq, at_ns, kind, decision, raw_hash):
    return digest(canonical([previous, seq, at_ns, kind, decision, raw_hash]).encode())


@dataclass(frozen=True)
class Limits:
    messages: int = 20_000
    raw_bytes: int = 8 * 1024 * 1024
    seconds: int = 48 * 60 * 60
    frame_bytes: int = MAX_FRAME
    sample_modulus: int = 64
    active_watches: int = 2
    daily_watches: int = 24
    watch_seconds: int = 600

    def validate(self):
        bounds = {"messages": MAX_EVENTS, "raw_bytes": 8 * 1024 * 1024,
                  "seconds": 172800, "frame_bytes": MAX_FRAME,
                  "sample_modulus": 1_000_000, "active_watches": 32,
                  "daily_watches": 1000, "watch_seconds": 600}
        if any(type(v) is not int or not 1 <= v <= bounds[k]
               for k, v in asdict(self).items()):
            raise CaptureError("invalid-limits")


def private_regular(path):
    st = path.lstat()
    if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
            or st.st_uid != os.getuid() or st.st_mode & 0o077):
        raise CaptureError("unsafe-file")
    return st


def private_directory(path):
    st = path.lstat()
    if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid()
            or st.st_mode & 0o077):
        raise CaptureError("unsafe-directory")


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def exclusive_file(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(content)
        out.flush()
        os.fsync(out.fileno())
    sync_dir(path.parent)


def lock(path, shared=False):
    private_directory(path)
    fd = os.open(path / "capture.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        private_regular(path / "capture.lock")
        fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        return fd
    except BaseException:
        os.close(fd)
        raise CaptureError("capture-locked-or-unsafe") from None


def connect(path, readonly=False):
    for member in path.parent.iterdir():
        if member.name not in {"ticks.db", "capture.lock", "ticks.db-journal"}:
            raise CaptureError("unexpected-capture-file")
        if private_regular(member).st_size > MAX_DB + 4096:
            raise CaptureError("capture-file-too-large")
    st = private_regular(path)
    if st.st_size > MAX_DB:
        raise CaptureError("database-too-large")
    db = sqlite3.connect(path.resolve().as_uri() + ("?mode=ro" if readonly else "?mode=rw"),
                         uri=True, timeout=1)
    try:
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("PRAGMA temp_store=MEMORY")
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_FRAME * 4)
        if readonly:
            db.execute("PRAGMA query_only=ON")
        else:
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            page = db.execute("PRAGMA page_size").fetchone()[0]
            db.execute(f"PRAGMA max_page_count={MAX_DB // page}")
        return db
    except BaseException:
        db.close()
        raise


SCHEMA = """
CREATE TABLE state(id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
CREATE TABLE events(seq INTEGER PRIMARY KEY, at_ns INTEGER NOT NULL,
 kind TEXT NOT NULL, decision TEXT NOT NULL, raw BLOB NOT NULL,
 raw_sha TEXT NOT NULL, chain_sha TEXT NOT NULL);
CREATE TABLE mints(mint TEXT PRIMARY KEY, first_ns INTEGER NOT NULL,
 day INTEGER NOT NULL, decision TEXT NOT NULL, until_ns INTEGER NOT NULL);
"""


def read_state(db):
    schema = db.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
    if set(schema) != {("table", "state"), ("table", "events"), ("table", "mints")}:
        raise CaptureError("unexpected-schema")
    row = db.execute("SELECT value FROM state WHERE id=1").fetchone()
    if not row:
        raise CaptureError("missing-state")
    s = json.loads(row[0])
    if s.get("version") != VERSION:
        raise CaptureError("unsupported-version")
    Limits(**s["limits"]).validate()
    return s


def put_state(db, state):
    db.execute("INSERT OR REPLACE INTO state VALUES(1,?)", (canonical(state),))


def strict_json(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError("duplicate")
            out[k] = v
        return out
    def constant(_):
        raise ValueError("nonfinite")
    def floating(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("nonfinite")
        return number
    row = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant,
                     parse_float=floating)
    if not isinstance(row, dict):
        raise ValueError("not-object")
    return row


def sensitive(row):
    """Reject credential-shaped fields anywhere; never store provider error text."""
    if isinstance(row, dict):
        for k, v in row.items():
            key = re.sub(r"[^a-z]", "", k.lower())
            if any(x in key for x in ("apikey", "privatekey", "secret", "password", "seedphrase", "authorization")):
                return True
            if sensitive(v):
                return True
    elif isinstance(row, list):
        return any(sensitive(x) for x in row)
    elif isinstance(row, str):
        return bool(re.search(r"(?:api[-_]?key=|bearer\s)", row, re.I))
    return False


class Capture:
    def __init__(self, directory, limits=Limits(), *, wall=time.time_ns,
                 monotonic=time.monotonic_ns, redactions=()):
        limits.validate()
        self.path = Path(directory)
        self.db = None
        self.fd = None
        self.wall = wall
        self.monotonic = monotonic
        self.redactions = tuple({variant.encode() for value in redactions if value
                                 for variant in (value, quote(value, safe=""), json.dumps(value)[1:-1])})
        self.limits = limits
        try:
            if not self.path.exists() and not self.path.is_symlink():
                self.path.mkdir(mode=0o700)
            self.fd = lock(self.path)
            dbpath = self.path / "ticks.db"
            new = not dbpath.exists() and not dbpath.is_symlink()
            if new:
                if set(p.name for p in self.path.iterdir()) != {"capture.lock"}:
                    raise CaptureError("directory-not-empty")
                exclusive_file(dbpath, b"")
            self.db = connect(dbpath)
            now = wall()
            if new:
                self.db.executescript(SCHEMA)
                self.state = dict(version=VERSION, limits=asdict(limits), start_ns=now,
                    deadline_ns=now + limits.seconds * 1_000_000_000, last_ns=now,
                    messages=0, raw_bytes=0, rows=0, gaps=0, restarts=0, gap_records=[],
                    chain_sha=GENESIS, status="paused", reason=None)
                with self.db:
                    put_state(self.db, self.state)
            else:
                self.state = read_state(self.db)
                if self.state["limits"] != asdict(limits):
                    raise CaptureError("limits-changed")
                validate_rows(self.db, self.state)
                if self.state["status"] == "active":
                    self._mark_gap(now, "unclean-shutdown")
                    self._stop("unclean-shutdown")
                elif self.state["status"] == "paused":
                    if self._mark_gap(now, "restart"):
                        self.state["restarts"] += 1
                        with self.db:
                            put_state(self.db, self.state)
            self.mono_start = monotonic()
            self.mono_last = self.mono_start
            self.wall_start = now
            if self.state["status"] != "stopped":
                self.state["status"] = "active"
                with self.db:
                    put_state(self.db, self.state)
                self.tick()
        except BaseException:
            self._release()
            raise

    def _release(self):
        if self.db is not None:
            self.db.close()
            self.db = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def _stop(self, reason):
        self.state["status"] = "stopped"
        self.state["reason"] = reason
        with self.db:
            put_state(self.db, self.state)
        return False

    def _storage_failed(self):
        self.db.rollback()
        # Read durable counters: a failed record transaction may have changed
        # Python values before SQLite rolled it back.
        try:
            self.state = read_state(self.db)
            self._stop("storage-error")
        except sqlite3.Error:
            pass
        self.state["status"] = "stopped"
        self.state["reason"] = "storage-error"
        raise CaptureError("storage-error") from None

    def tick(self):
        try:
            return self._tick()
        except sqlite3.Error:
            self._storage_failed()

    def _tick(self):
        if self.state["status"] != "active":
            return False
        now, mono = self.wall(), self.monotonic()
        if now < self.state["last_ns"] or mono < self.mono_last:
            return self._stop("clock-regression")
        self.mono_last = mono
        elapsed = mono - self.mono_start
        if now >= self.state["deadline_ns"] or self.wall_start + elapsed >= self.state["deadline_ns"]:
            return self._stop("deadline")
        self.state["last_ns"] = now
        with self.db:
            put_state(self.db, self.state)
        return True

    def _mark_gap(self, now, reason):
        if len(self.state["gap_records"]) >= 128:
            return self._stop("gap-limit")
        self.state["gap_records"].append({"after_seq": self.state["rows"], "at_ns": now, "reason": reason})
        self.state["gaps"] += 1
        with self.db:
            self.db.execute("UPDATE mints SET until_ns=0")
            put_state(self.db, self.state)
        return True

    def gap(self):
        if not self.tick():
            return False
        # Until transport/recovery is proven, disconnect means stop, not retry.
        self._mark_gap(self.wall(), "transport-gap")
        return self._stop("transport-gap")

    def receive(self, raw):
        try:
            return self._receive(raw)
        except sqlite3.Error:
            self._storage_failed()

    def _receive(self, raw):
        if not self.tick():
            return None
        if type(raw) is not bytes:
            self._stop("invalid-frame-type")
            return None
        self.state["messages"] += 1
        # Reserve the message before validation/write. A crash leaves an active
        # session, which cannot resume and silently reset its counters.
        with self.db:
            put_state(self.db, self.state)
        if len(raw) > self.limits.frame_bytes:
            self._stop("frame-limit")
            return None
        if self.state["raw_bytes"] + len(raw) > self.limits.raw_bytes:
            self._stop("raw-byte-limit")
            return None
        if any(token in raw for token in self.redactions):
            self._stop("credential-in-frame")
            return None
        try:
            row = strict_json(raw)
            if sensitive(row):
                self._stop("credential-in-frame")
                return None
            if row.get("error") or row.get("errors"):
                self._stop("provider-error")
                return None
            kind = row.get("txType")
            if kind is None and set(row) <= {"message"} and isinstance(row.get("message"), str):
                # Acknowledgement bodies can echo credentials/URLs. Count only.
                decision = "control-discarded"
            elif kind in {"create", "buy", "sell", "migration", "migrate"}:
                mint, sig = row.get("mint"), row.get("signature")
                if not (isinstance(mint, str) and 32 <= len(mint) <= 44 and BASE58.fullmatch(mint)
                        and isinstance(sig, str) and 64 <= len(sig) <= 88 and BASE58.fullmatch(sig)):
                    raise ValueError("identity")
                decision = self._record(row, raw)
            else:
                raise ValueError("kind")
        except (ValueError, UnicodeError, RecursionError, TypeError):
            self._stop("invalid-frame")
            return None
        if self.state["messages"] >= self.limits.messages:
            self._stop("message-limit")
        elif self.state["raw_bytes"] >= self.limits.raw_bytes:
            self._stop("raw-byte-limit")
        return decision

    def _record(self, row, raw):
        mint, kind, now = row["mint"], row["txType"], self.state["last_ns"]
        prior = self.db.execute("SELECT decision,until_ns FROM mints WHERE mint=?", (mint,)).fetchone()
        with self.db:
            if kind == "create":
                if prior:
                    decision = "duplicate-create"
                else:
                    day = now // 86_400_000_000_000
                    selected = int(digest(mint.encode()), 16) % self.limits.sample_modulus == 0
                    active = self.db.execute("SELECT count(*) FROM mints WHERE until_ns>?", (now,)).fetchone()[0]
                    daily = self.db.execute("SELECT count(*) FROM mints WHERE day=? AND decision='watch-planned'", (day,)).fetchone()[0]
                    decision = ("sample-excluded" if not selected else
                                "active-cap" if active >= self.limits.active_watches else
                                "daily-cap" if daily >= self.limits.daily_watches else "watch-planned")
                    until = now + self.limits.watch_seconds * 1_000_000_000 if decision == "watch-planned" else 0
                    self.db.execute("INSERT INTO mints VALUES(?,?,?,?,?)", (mint, now, day, decision, until))
            else:
                decision = "within-planned-watch" if prior and prior[1] > now else "outside-planned-watch"
                if kind in {"migration", "migrate"}:
                    self.db.execute("UPDATE mints SET until_ns=0 WHERE mint=?", (mint,))
            seq, raw_hash = self.state["rows"] + 1, digest(raw)
            linked = chain(self.state["chain_sha"], seq, now, kind, decision, raw_hash)
            self.db.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?)", (seq, now, kind, decision, raw, raw_hash, linked))
            self.state.update(rows=seq, chain_sha=linked, raw_bytes=self.state["raw_bytes"] + len(raw))
            put_state(self.db, self.state)
        return decision

    def close(self):
        try:
            if self.db is not None and self.state["status"] == "active":
                self.state["status"] = "paused"
                with self.db:
                    put_state(self.db, self.state)
        finally:
            self._release()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, tb):
        if kind is not None and self.db is not None:
            try:
                if self.state["status"] == "active":
                    self._stop("interrupted")
            finally:
                self._release()
        else:
            self.close()


def validate_rows(db, s):
    if s["status"] not in {"active", "paused", "stopped"}:
        raise CaptureError("invalid-state")
    if not (0 <= s["rows"] <= s["messages"] <= s["limits"]["messages"]
            and 0 <= s["raw_bytes"] <= s["limits"]["raw_bytes"]):
        raise CaptureError("invalid-counters")
    reasons = {None, "unclean-shutdown", "gap-limit", "clock-regression", "deadline",
               "transport-gap", "invalid-frame-type", "frame-limit", "raw-byte-limit",
               "credential-in-frame", "provider-error", "invalid-frame", "storage-error",
               "message-limit", "interrupted"}
    if s["reason"] not in reasons or (s["status"] == "stopped") != (s["reason"] is not None):
        raise CaptureError("invalid-stop-reason")
    gaps = s["gap_records"]
    if len(gaps) > 128 or s["gaps"] != len(gaps) or s["restarts"] != sum(g["reason"] == "restart" for g in gaps):
        raise CaptureError("gap-integrity")
    if any(set(g) != {"after_seq", "at_ns", "reason"} or type(g["at_ns"]) is not int
           or type(g["after_seq"]) is not int or not 0 <= g["after_seq"] <= s["rows"]
           or g["reason"] not in {"restart", "unclean-shutdown", "transport-gap"} for g in gaps):
        raise CaptureError("gap-integrity")
    gap_after = {g["after_seq"] for g in gaps}
    count, total, previous, last = 0, 0, GENESIS, s["start_ns"]
    expected = {}
    for seq, at, kind, decision, raw, raw_hash, linked in db.execute("SELECT * FROM events ORDER BY seq LIMIT ?", (MAX_EVENTS + 1,)):
        count += 1
        if (count > MAX_EVENTS or seq != count or at < last or at > s["last_ns"]
                or type(raw) is not bytes or len(raw) > s["limits"]["frame_bytes"]
                or digest(raw) != raw_hash
                or chain(previous, seq, at, kind, decision, raw_hash) != linked):
            raise CaptureError("replay-integrity")
        total += len(raw)
        previous, last = linked, at
        payload = strict_json(raw)
        mint = payload.get("mint")
        if payload.get("txType") != kind:
            raise CaptureError("event-integrity")
        if kind == "create":
            if mint in expected:
                if decision != "duplicate-create":
                    raise CaptureError("mint-integrity")
            else:
                if decision not in {"watch-planned", "sample-excluded", "active-cap", "daily-cap"}:
                    raise CaptureError("mint-integrity")
                until = at + s["limits"]["watch_seconds"] * 1_000_000_000 if decision == "watch-planned" else 0
                expected[mint] = [at, at // 86_400_000_000_000, decision, until]
        else:
            if kind not in {"buy", "sell", "migration", "migrate"}:
                raise CaptureError("event-integrity")
            wanted = "within-planned-watch" if mint in expected and expected[mint][3] > at else "outside-planned-watch"
            if decision != wanted:
                raise CaptureError("mint-integrity")
            if kind in {"migration", "migrate"} and mint in expected:
                expected[mint][3] = 0
        if seq in gap_after:
            for entry in expected.values():
                entry[3] = 0
    if (count, total, previous) != (s["rows"], s["raw_bytes"], s["chain_sha"]):
        raise CaptureError("replay-integrity")
    actual = {row[0]: list(row[1:]) for row in db.execute("SELECT * FROM mints LIMIT ?", (MAX_EVENTS + 1,))}
    if actual != expected:
        raise CaptureError("mint-integrity")


@contextmanager
def checked(directory):
    path = Path(directory)
    fd = lock(path, shared=True)
    db = None
    try:
        db = connect(path / "ticks.db", readonly=True)
        if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise CaptureError("sqlite-integrity")
        state = read_state(db)
        if state["status"] == "active":
            raise CaptureError("unclean-shutdown")
        validate_rows(db, state)
        yield db, state
    finally:
        if db is not None:
            db.close()
        os.close(fd)


def report(db, state):
    decisions = dict(db.execute("SELECT decision,count(*) FROM mints GROUP BY decision"))
    return {"status": "offline-capture-verified-live-blocked", "messages": state["messages"],
            "raw_rows": state["rows"], "raw_bytes": state["raw_bytes"],
            "chain_sha256": state["chain_sha"], "gaps": state["gaps"],
            "gap_records": state["gap_records"],
            "restarts": state["restarts"], "capture_status": state["status"],
            "stop_reason": state["reason"], "mint_decisions": decisions,
            "ledger_order_verified": False, "initial_state_verified": False,
            "subscription_installed": False, "billing_limit_verified": False,
            "profitability_evaluated": False}


def verify(directory):
    with checked(directory) as (db, state):
        return report(db, state)


def export_capture(directory, destination):
    """Closed, locked source -> exclusive private copy plus pinned digest."""
    destination = Path(destination)
    with checked(directory) as (db, state):
        destination.mkdir(mode=0o700)  # refuse replacement, including symlinks
        source = Path(directory) / "ticks.db"
        # A bounded source is copied byte-for-byte while the capture lock is held.
        data = source.read_bytes()
        exclusive_file(destination / "ticks.db", data)
        manifest = {"version": VERSION, "database_sha256": digest(data), "report": report(db, state)}
        exclusive_file(destination / "manifest.json", canonical(manifest).encode())
        return manifest


def restore_capture(archive, destination):
    archive, destination = Path(archive), Path(destination)
    private_directory(archive)
    if set(p.name for p in archive.iterdir()) != {"ticks.db", "manifest.json"}:
        raise CaptureError("archive-members")
    if private_regular(archive / "manifest.json").st_size > 16_384:
        raise CaptureError("manifest-too-large")
    if private_regular(archive / "ticks.db").st_size > MAX_DB:
        raise CaptureError("database-too-large")
    manifest = json.loads((archive / "manifest.json").read_bytes())
    data = (archive / "ticks.db").read_bytes()
    if manifest.get("version") != VERSION or digest(data) != manifest["database_sha256"]:
        raise CaptureError("archive-checksum")
    destination.mkdir(mode=0o700)
    exclusive_file(destination / "ticks.db", data)
    actual = verify(destination)
    if actual != manifest["report"]:
        raise CaptureError("archive-report")
    return actual
