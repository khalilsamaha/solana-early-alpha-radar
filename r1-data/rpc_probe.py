"""Small public-mainnet RPC feasibility probe; never signs, simulates or sends.

Public RPC responses are provider-reported evidence, not cryptographic proofs.
The live CLI requires --read-public-rpc. Offline checks inject all HTTP responses.
"""
import argparse
from contextlib import contextmanager
import gzip
import hashlib
import os
from pathlib import Path
import signal
import sqlite3
import stat
import sys
import threading
import time
import urllib.error
import urllib.request

from capture import CaptureError, canonical, exclusive_file, strict_json, sync_dir
from source_probe import discover_database

ENDPOINT = "https://api.mainnet.solana.com"
GENESIS = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"
TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
PROGRAMS = {TOKEN, TOKEN_2022}
ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
MAX_RESPONSE = 1024 * 1024
MAX_REQUESTS = 9


def identifier(value, size):
    if not isinstance(value, str) or not 1 <= len(value) <= 90:
        return False
    number = 0
    for char in value:
        if char not in ALPHABET:
            return False
        number = number * 58 + ALPHABET.index(char)
    return len(value) - len(value.lstrip("1")) + (number.bit_length() + 7) // 8 == size


def integer(value, ceiling=2**64 - 1):
    return type(value) is int and 0 <= value <= ceiling


def candidates(database, *, now_ms=None):
    """At most 32 indexed creation records -> up to three distinct transactions."""
    path = Path(database).absolute()
    identity = path.lstat()
    if path.resolve() != path or not stat.S_ISREG(identity.st_mode):
        raise CaptureError("database-path")
    now = time.time_ns() // 1_000_000 if now_ms is None else now_ms
    deadline = time.monotonic() + 3
    db = None
    picked, signatures, mints = [], set(), set()
    inspected, rejected = 0, 0
    try:
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("PRAGMA cache_size=-2048")
        db.execute("PRAGMA mmap_size=0")
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 16_384)
        db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 100)
        db.execute("BEGIN")
        if db.execute("SELECT type FROM sqlite_master WHERE name='launch_registry'").fetchone() != ("table",):
            raise CaptureError("missing-registry")
        if [r[2] for r in db.execute("PRAGMA index_info('launch_registry_received')")] != ["received_at"]:
            raise CaptureError("missing-index")
        def authorize(action, a, b, dbname, trigger):
            if action == sqlite3.SQLITE_SELECT:
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_READ and a == "launch_registry" and b in {"mint", "received_at", "data"}:
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_FUNCTION and b in {"typeof", "length"}:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        db.set_authorizer(authorize)
        rows = db.execute("""SELECT mint,received_at,
          CASE WHEN typeof(data)='text' AND length(CAST(data AS BLOB))<=4096 THEN data END
          FROM launch_registry INDEXED BY launch_registry_received
          WHERE received_at>=? AND received_at<=? ORDER BY received_at DESC LIMIT 32""",
          (now - 86_400_000, now - 120_000))
        for mint, at, raw in rows:
            if time.monotonic() >= deadline:
                raise CaptureError("read-deadline")
            inspected += 1
            try:
                row = strict_json(raw.encode())
                signature = row["fields"]["signature"]
                if (row.get("mint") != mint or row.get("source") != "pumpportal:create"
                        or row.get("version") != "launch-registry-1"
                        or row.get("receivedAt") != at or row.get("availableAt") != at
                        or not identifier(mint, 32) or not identifier(signature, 64)):
                    raise ValueError("invalid-identity")
                if signature in signatures or mint in mints:
                    rejected += 1
                    continue
                signatures.add(signature)
                mints.add(mint)
                picked.append({"mint": mint, "signature": signature, "received_at_ms": at})
            except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
                rejected += 1
            if len(picked) == 3:
                break
        after = path.lstat()
        if (identity.st_dev, identity.st_ino) != (after.st_dev, after.st_ino) or time.monotonic() >= deadline:
            raise CaptureError("source-changed-or-deadline")
    finally:
        if db is not None:
            db.close()
    return picked, {"records_inspected": inspected, "rejected_or_duplicate": rejected,
                    "selected": len(picked), "cutoff_at_ms": now,
                    "selection": "latest-three-distinct-valid-creations-aged-2min-to-24h-from-at-most-32-records"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@contextmanager
def alarm(seconds):
    """Bound DNS, headers and slow/trickling bodies, not just socket inactivity."""
    if threading.current_thread() is not threading.main_thread() or any(signal.getitimer(signal.ITIMER_REAL)):
        raise CaptureError("timer-unavailable")
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*_):
        raise TimeoutError()
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class Client:
    METHODS = {"getGenesisHash", "getSignatureStatuses", "getTransaction", "getAccountInfo"}

    def __init__(self, opener=None, *, clock=time.monotonic, pause=time.sleep):
        self.clock, self.pause = clock, pause
        self.deadline = clock() + 30
        self.calls, self.evidence = [], []
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.stopped = False

    def request(self, method, params):
        if method not in self.METHODS:
            raise CaptureError("rpc-method-forbidden")
        if self.stopped or len(self.calls) >= MAX_REQUESTS or self.clock() >= self.deadline:
            return {"state": "request-budget-exhausted"}
        if self.calls:
            self.pause(min(0.5, max(0, self.deadline - self.clock())))
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            self.stopped = True
            return {"state": "request-budget-exhausted"}
        request_id = len(self.calls) + 1
        entry = {"method": method, "id": request_id, "state": "pending"}
        self.calls.append(entry)
        request = urllib.request.Request(ENDPOINT, method="POST", headers={"Content-Type": "application/json"},
            data=canonical({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}).encode())
        started = self.clock()
        result = {"state": "rpc-unavailable"}
        try:
            with alarm(min(5, remaining)):
                with self.opener.open(request, timeout=min(5, remaining)) as response:
                    raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise CaptureError("response-too-large")
                envelope = strict_json(raw)
                if (envelope.get("jsonrpc") != "2.0" or type(envelope.get("id")) is not int
                        or envelope["id"] != request_id or "error" in envelope or "result" not in envelope):
                    raise CaptureError("rpc-envelope")
                result = {"state": "received", "result": envelope["result"]}
        except urllib.error.HTTPError as exc:
            result = {"state": "http-error", "http_status": exc.code}
            exc.close()
        except Exception:
            pass  # raw provider errors, bodies and request repr never enter reports
        if result["state"] != "received":
            self.stopped = True  # no retry, endpoint fallback or continued traffic
        entry.update(state=result["state"], elapsed_ms=round((self.clock() - started) * 1000))
        if "http_status" in result:
            entry["http_status"] = result["http_status"]
        # Private replay bundle contains successful public-chain evidence only;
        # failed response text is discarded. No API key is ever loaded.
        self.evidence.append({"method": method, "params": params, "response": result})
        return result


def transaction_facts(candidate, status, context_slot, tx):
    """Validate narrow provider-reported identity and parsed SPL initialization."""
    if status is None:
        return {"state": "signature-not-found-unknown"}
    if not isinstance(status, dict) or status.get("confirmationStatus") != "finalized":
        return {"state": "not-finalized"}
    slot = status.get("slot")
    if not integer(slot) or not integer(context_slot) or context_slot < slot or "err" not in status:
        raise ValueError("invalid-status")
    if status["err"] is not None:
        return {"state": "transaction-failed"}
    if tx is None:
        return {"state": "transaction-history-unavailable"}
    if not isinstance(tx, dict) or not integer(tx.get("slot")) or tx["slot"] != slot:
        raise ValueError("slot-mismatch")
    if tx.get("version") != "legacy" and not (type(tx.get("version")) is int and tx["version"] == 0):
        raise ValueError("transaction-version")
    transaction, meta = tx["transaction"], tx["meta"]
    signatures = transaction["signatures"]
    if (not isinstance(signatures, list) or not 1 <= len(signatures) <= 64
            or signatures[0] != candidate["signature"] or not all(identifier(s, 64) for s in signatures)
            or not isinstance(meta, dict) or "err" not in meta or meta["err"] is not None):
        raise ValueError("transaction-identity-or-success")
    message = transaction["message"]
    keys = message["accountKeys"]
    if not isinstance(keys, list) or not 1 <= len(keys) <= 256:
        raise ValueError("account-keys")
    pubkeys = [k.get("pubkey") if isinstance(k, dict) else None for k in keys]
    if (not all(identifier(k, 32) for k in pubkeys) or len(set(pubkeys)) != len(pubkeys)
            or candidate["mint"] not in pubkeys
            or any(type(k.get("signer")) is not bool for k in keys)
            or sum(k["signer"] for k in keys) != len(signatures)):
        raise ValueError("mint-membership-or-signers")
    instructions = message["instructions"]
    if not isinstance(instructions, list) or len(instructions) > 256:
        raise ValueError("instructions")
    all_instructions = list(instructions)
    inner = meta.get("innerInstructions")
    if inner is not None:
        if not isinstance(inner, list) or len(inner) > 256:
            raise ValueError("inner-instructions")
        seen = set()
        for group in inner:
            idx, items = group["index"], group["instructions"]
            if not integer(idx, len(instructions) - 1) or idx in seen or not isinstance(items, list):
                raise ValueError("inner-index")
            seen.add(idx)
            all_instructions.extend(items)
    if len(all_instructions) > 1024:
        raise ValueError("instruction-cap")
    matches = []
    for ins in all_instructions:
        if not isinstance(ins, dict):
            raise ValueError("instruction")
        parsed = ins.get("parsed")
        if ins.get("programId") not in PROGRAMS or not isinstance(parsed, dict):
            continue
        if parsed.get("type") not in {"initializeMint", "initializeMint2"}:
            continue
        info = parsed.get("info")
        if not isinstance(info, dict) or info.get("mint") != candidate["mint"]:
            continue
        if not integer(info.get("decimals"), 255):
            raise ValueError("decimals")
        matches.append((ins["programId"], info["decimals"]))
    if len(matches) != 1:
        return {"state": "initialization-not-uniquely-observed", "slot": slot}
    return {"state": "initialization-observed", "slot": slot,
            "token_program": matches[0][0], "decimals": matches[0][1]}


def account_matches(facts, account):
    if (not isinstance(account, dict) or not isinstance(account.get("context"), dict)
            or not integer(account["context"].get("slot"))):
        return False
    value = account.get("value")
    if account["context"]["slot"] < facts["slot"] or not isinstance(value, dict):
        return False
    parsed = value.get("data", {}).get("parsed", {}) if isinstance(value.get("data"), dict) else {}
    if not isinstance(parsed, dict):
        return False
    info = parsed.get("info", {})
    return (value.get("owner") == facts["token_program"] and value.get("executable") is False
            and parsed.get("type") == "mint" and isinstance(info, dict)
            and info.get("isInitialized") is True and integer(info.get("decimals"), 255)
            and info["decimals"] == facts["decimals"])


def reconcile(picked, client):
    if not 1 <= len(picked) <= 3 or any(not identifier(p.get("signature"), 64) or not identifier(p.get("mint"), 32) for p in picked):
        raise CaptureError("invalid-candidates")
    if len({p["signature"] for p in picked}) != len(picked) or len({p["mint"] for p in picked}) != len(picked):
        raise CaptureError("duplicate-candidates")
    result = {"status": "rpc-feasibility-incomplete", "cases": [], "genesis_verified_before_and_after": False,
              "creator_verified": False, "curve_state_verified": False, "ledger_order_verified": False,
              "profitability_evaluated": False, "paid_collection_enabled": False, "transactions_sent": 0}
    before = client.request("getGenesisHash", [])
    if before.get("result") != GENESIS or before["state"] != "received":
        return result
    statuses = client.request("getSignatureStatuses", [[p["signature"] for p in picked], {"searchTransactionHistory": True}])
    body = statuses.get("result")
    if (statuses["state"] != "received" or not isinstance(body, dict)
            or not isinstance(body.get("value"), list) or len(body["value"]) != len(picked)
            or not isinstance(body.get("context"), dict)
            or not integer(body["context"].get("slot"))):
        return result
    context = body["context"]["slot"]
    for index, (candidate, status) in enumerate(zip(picked, body["value"]), 1):
        item = {"case": index, "state": "rpc-unavailable"}
        result["cases"].append(item)
        try:
            if status is None or not isinstance(status, dict) or status.get("confirmationStatus") != "finalized" or status.get("err") is not None:
                item.update(transaction_facts(candidate, status, context, None))
                continue
            tx = client.request("getTransaction", [candidate["signature"],
                {"commitment": "finalized", "encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
            if tx["state"] != "received":
                break
            facts = transaction_facts(candidate, status, context, tx["result"])
            item.update(facts)
            if facts["state"] == "initialization-observed":
                account = client.request("getAccountInfo", [candidate["mint"],
                    {"commitment": "finalized", "encoding": "jsonParsed", "minContextSlot": facts["slot"]}])
                if account["state"] != "received":
                    item["state"] = "account-unavailable"
                    break
                item["state"] = "rpc-facts-reconciled" if account_matches(facts, account["result"]) else "account-not-reconciled"
        except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
            item["state"] = "inconsistent-or-unsupported-evidence"
    after = client.request("getGenesisHash", [])
    if after["state"] == "received" and after.get("result") == GENESIS:
        result["genesis_verified_before_and_after"] = True
    else:
        for item in result["cases"]:
            if item["state"] == "rpc-facts-reconciled":
                item["state"] = "genesis-recheck-unavailable"
    if (result["genesis_verified_before_and_after"] and len(result["cases"]) == len(picked)
            and all(c["state"] == "rpc-facts-reconciled" for c in result["cases"])):
        result["status"] = "rpc-facts-reconciled-live-blocked"
    return result


def replay_bundle(bundle):
    if bundle.get("schema_version") != 1 or not isinstance(bundle.get("rpc_evidence"), list) or len(bundle["rpc_evidence"]) > MAX_REQUESTS:
        raise CaptureError("invalid-replay-bundle")
    records = bundle["rpc_evidence"]
    class Replay:
        def __init__(self):
            self.index = 0
            self.stopped = False
        def request(self, method, params):
            if self.stopped or self.index == len(records):
                return {"state": "request-budget-exhausted"}
            item = records[self.index]
            if item["method"] != method or item["params"] != params:
                raise CaptureError("replay-request-mismatch")
            self.index += 1
            result = item["response"]
            if result["state"] != "received":
                self.stopped = True
            return result
    replay = Replay()
    result = reconcile(bundle["candidates"], replay)
    if replay.index != len(records):
        raise CaptureError("unused-replay-evidence")
    return result


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CaptureError("invalid-arguments")


def main(argv=None):
    try:
        p = Parser(description=__doc__)
        p.add_argument("--project", required=True)
        p.add_argument("--output-directory", required=True)
        p.add_argument("--read-public-rpc", action="store_true", required=True)
        a = p.parse_args(argv)
        out = Path(a.output_directory)
        out.mkdir(mode=0o700)  # exclusive run directory; never replace prior evidence
        report = {"status": "source-unavailable", "endpoint": ENDPOINT, "credentials_loaded": False,
                  "paid_collection_enabled": False, "transactions_sent": 0, "rpc_requests": [],
                  "selection": None, "reconciliation": None}
        bundle = {"schema_version": 1, "candidates": [], "rpc_evidence": []}
        client = None
        try:
            picked, selection = candidates(discover_database(a.project))
            bundle["candidates"] = picked
            report["selection"] = selection
            report["status"] = "no-eligible-creation-records"
            if picked:
                client = Client()
                report["reconciliation"] = reconcile(picked, client)
                report["status"] = report["reconciliation"]["status"]
        except Exception:
            report["status"] = "probe-unavailable"
        finally:
            if client is not None:
                report["rpc_requests"] = client.calls
                bundle["rpc_evidence"] = client.evidence
        report["local_replay_verified"] = False
        if report["reconciliation"] is not None:
            if replay_bundle(bundle) != report["reconciliation"]:
                raise CaptureError("replay-disagreement")
            report["local_replay_verified"] = True
        root = Path(__file__).resolve().parent
        report["source_sha256"] = {n: hashlib.sha256((root / n).read_bytes()).hexdigest()
                                   for n in ("rpc_probe.py", "source_probe.py", "capture.py")}
        raw = canonical(bundle).encode()
        if len(raw) > 32 * 1024 * 1024:
            raise CaptureError("evidence-cap")
        evidence = gzip.compress(raw, mtime=0)
        report["evidence_sha256"] = hashlib.sha256(evidence).hexdigest()
        report["evidence_decoded_sha256"] = hashlib.sha256(raw).hexdigest()
        report["evidence_file"] = "evidence.json.gz"
        report["limitations"] = ["provider-reported facts, not independent cryptographic proofs",
            "three-case feasibility only, no throughput or historical recovery guarantee",
            "mint initialization is not verified Pump creator identity",
            "no curve reserve, fee-version, intra-slot ordering or profit verification",
            "public-endpoint failure does not imply token failure",
            "evidence retained locally; off-machine preservation remains unverified"]
        exclusive_file(out / "evidence.json.gz", evidence)
        retained = (out / "evidence.json.gz").read_bytes()
        if hashlib.sha256(retained).hexdigest() != report["evidence_sha256"] or gzip.decompress(retained) != raw:
            raise CaptureError("retained-evidence-mismatch")
        if report["local_replay_verified"] and replay_bundle(strict_json(gzip.decompress(retained))) != report["reconciliation"]:
            raise CaptureError("retained-replay-disagreement")
        exclusive_file(out / "report.json", (canonical(report) + "\n").encode())
        if os.geteuid() == 0 and os.environ.get("SUDO_UID", "").isdigit() and os.environ.get("SUDO_GID", "").isdigit():
            uid, gid = int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"])
            for path in (out / "report.json", out / "evidence.json.gz", out):
                os.chown(path, uid, gid)
        sync_dir(out.parent)
        print("R1 RPC probe:", report["status"], "— live collection remains blocked.")
        return 0
    except Exception:
        print("R1 RPC probe stopped; no source acceptance is granted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
