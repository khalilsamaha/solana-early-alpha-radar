"""Offline inspection of accepted RPC bundles; no source or network access.

Exact schema consumption is mandatory. Unknown event tails are reported without
exporting partially decoded values. This is evidence inspection, not simulation.
"""
import gzip
import hashlib
import io
import os
from pathlib import Path
import stat
import sys
import tempfile

from capture import CaptureError, canonical, exclusive_file, strict_json, sync_dir
import rpc_probe as rpc

ROOT = Path(__file__).resolve().parent
SCHEMA_SHA256 = "5f363ffd904f53f9330df55ad926e89bb21ec37719df0c9ede73cfb889e8571d"
EVENT_TAG = bytes.fromhex("e445a52e51cb9a1d")
SYSTEM = "1" * 32
WSOL = "So11111111111111111111111111111111111111112"
MAX_INPUT = 32 * 1024 * 1024
SOURCES = ("event_inspect.py", "pump_schema.json", "rpc_probe.py", "source_probe.py", "capture.py")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def schema():
    raw = (ROOT / "pump_schema.json").read_bytes()
    if sha(raw) != SCHEMA_SHA256:
        raise CaptureError("schema-pin-mismatch")
    return strict_json(raw)


def b58decode(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 6000:
        raise CaptureError("base58-size")
    n = 0
    for c in value:
        if c not in rpc.ALPHABET:
            raise CaptureError("base58-character")
        n = n * 58 + rpc.ALPHABET.index(c)
    raw = b"\0" * (len(value) - len(value.lstrip("1"))) + n.to_bytes((n.bit_length() + 7) // 8, "big")
    if len(raw) > 4096:
        raise CaptureError("instruction-size")
    return raw


def b58encode(raw):
    n, encoded = int.from_bytes(raw, "big"), ""
    while n:
        n, remainder = divmod(n, 58)
        encoded = rpc.ALPHABET[remainder] + encoded
    return "1" * (len(raw) - len(raw.lstrip(b"\0"))) + encoded


class SchemaMismatch(CaptureError):
    def __init__(self, remaining):
        self.remaining = remaining
        super().__init__("unconsumed-event-bytes")


def decode_event(raw, spec, layout):
    if not 8 <= len(raw) <= 4096 or raw[:8] != bytes(spec["discriminator"]):
        raise CaptureError("event-discriminator-or-size")
    types = {t["name"]: t["type"]["fields"] for t in layout["types"]}
    position = 8
    def take(n):
        nonlocal position
        if n < 0 or position + n > len(raw):
            raise CaptureError("truncated-event")
        value = raw[position:position+n]
        position += n
        return value
    def value(kind):
        if kind == "pubkey":
            return b58encode(take(32))
        if kind == "string":
            n = int.from_bytes(take(4), "little")
            if n > 512:
                raise CaptureError("event-string-cap")
            return take(n).decode("utf-8", errors="strict")
        if isinstance(kind, str) and kind in {"u8", "u16", "u64", "i64", "bool"}:
            n = int.from_bytes(take({"u8": 1, "u16": 2, "u64": 8, "i64": 8, "bool": 1}[kind]), "little", signed=kind == "i64")
            if kind == "bool":
                if n not in (0, 1):
                    raise CaptureError("invalid-bool")
                return bool(n)
            return n
        if isinstance(kind, dict) and "vec" in kind:
            n = int.from_bytes(take(4), "little")
            if n > 16:
                raise CaptureError("event-vector-cap")
            return [value(kind["vec"]) for _ in range(n)]
        if isinstance(kind, dict) and "defined" in kind:
            return {f["name"]: value(f["type"]) for f in types[kind["defined"]["name"]]}
        raise CaptureError("unsupported-field-type")
    result = {f["name"]: value(f["type"]) for f in types[spec["name"]]}
    if position != len(raw):
        raise SchemaMismatch(len(raw) - position)
    return result


def account_roles(ins, name, layout, keys):
    definition = next(x for x in layout["instructions"] if x["name"] == name)
    if ins.get("programId") != layout["program_id"] or type(ins.get("stackHeight")) is not int or ins["stackHeight"] != 1:
        raise CaptureError("unsupported-parent")
    if b58decode(ins.get("data"))[:8] != bytes(definition["discriminator"]):
        raise CaptureError("parent-discriminator")
    accounts = ins.get("accounts")
    # This increment supports only direct SOL create_v2 (16) / buy_v2 (27).
    # Remaining accounts, CPI wrappers and other instruction versions stay unknown.
    if not isinstance(accounts, list) or len(accounts) != len(definition["accounts"]):
        raise CaptureError("unsupported-account-layout")
    roles = {}
    for definition, pubkey in zip(definition["accounts"], accounts):
        if pubkey not in keys or ("address" in definition and pubkey != definition["address"]):
            raise CaptureError("account-role-mismatch")
        roles[definition["name"]] = pubkey
    if roles["program"] != layout["program_id"]:
        raise CaptureError("program-account-mismatch")
    return roles


def token_units(value):
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or len(value) > 20:
        raise CaptureError("token-amount")
    number = int(value)
    if not rpc.integer(number):
        raise CaptureError("token-range")
    return number


def inspect_case(candidate, tx, facts, layout):
    keys = {k["pubkey"]: k for k in tx["transaction"]["message"]["accountKeys"]}
    top = tx["transaction"]["message"]["instructions"]
    groups = tx["meta"].get("innerInstructions")
    if not isinstance(groups, list):
        raise CaptureError("missing-inner-evidence")
    records = []
    for group in groups:
        for position, ins in enumerate(group["instructions"]):
            if ins.get("programId") != layout["program_id"] or "data" not in ins:
                continue
            data = b58decode(ins["data"])
            if data[:8] != EVENT_TAG:
                raise CaptureError("unsupported-pump-self-cpi")
            event = next((e for e in layout["events"] if bytes(e["discriminator"]) == data[8:16]), None)
            if event is None:
                raise CaptureError("unknown-pump-event")
            name = "create_v2" if event["name"] == "CreateEvent" else "buy_v2"
            roles = account_roles(top[group["index"]], name, layout, keys)
            if type(ins.get("stackHeight")) is not int or ins["stackHeight"] != 2 or ins.get("accounts") != [roles["event_authority"]]:
                raise CaptureError("event-cpi-provenance")
            record = {"kind": event["name"], "parent_index": group["index"], "inner_index": position,
                      "payload_bytes": len(data) - 8, "payload_sha256": sha(data[8:]),
                      "roles": roles, "instructions": group["instructions"]}
            try:
                record["value"] = decode_event(data[8:], event, layout)
                record["state"] = "exact-schema-match"
            except SchemaMismatch as exc:
                record.update(state="schema-mismatch", unconsumed_bytes=exc.remaining)
            records.append(record)
    creates = [r for r in records if r["kind"] == "CreateEvent"]
    trades = [r for r in records if r["kind"] == "TradeEvent"]
    if len(creates) != 1 or creates[0]["state"] != "exact-schema-match":
        raise CaptureError("creation-not-unique-or-unsupported")
    create, roles = creates[0]["value"], creates[0]["roles"]
    mint = candidate["mint"]
    if (create["mint"] != mint or roles["mint"] != mint
            or create["bonding_curve"] != roles["bonding_curve"] or create["user"] != roles["user"]
            or create["token_program"] != roles["token_program"] or create["token_program"] != facts["token_program"]
            or create["quote_mint"] != SYSTEM or not keys[roles["mint"]]["signer"] or not keys[roles["user"]]["signer"]):
        raise CaptureError("creation-identity-or-quote")
    # Cover every direct Pump invocation; no missing buy event can imply no buy.
    pump_parents = [i for i, ins in enumerate(top) if ins.get("programId") == layout["program_id"]]
    if sorted(pump_parents) != sorted(r["parent_index"] for r in records):
        raise CaptureError("missing-or-duplicate-parent-event")
    mint_to = []
    for ins in creates[0]["instructions"]:
        parsed = ins.get("parsed")
        if ins.get("programId") == facts["token_program"] and isinstance(parsed, dict) and parsed.get("type") == "mintTo":
            info = parsed["info"]
            if info["mint"] == mint:
                mint_to.append(token_units(info["amount"]))
    if not mint_to:
        raise CaptureError("missing-mint-to")
    public_events = []
    for record in records:
        public = {k: record[k] for k in ("kind", "parent_index", "inner_index", "payload_bytes", "payload_sha256", "state")}
        if "unconsumed_bytes" in record:
            public["unconsumed_bytes"] = record["unconsumed_bytes"]
        public_events.append(public)
    transfers = []
    for trade in trades:
        r = trade["roles"]
        if (trade["parent_index"] <= creates[0]["parent_index"] or r["base_mint"] != mint
                or r["bonding_curve"] != create["bonding_curve"] or r["quote_mint"] != WSOL
                or r["base_token_program"] != facts["token_program"] or not keys[r["user"]]["signer"]):
            raise CaptureError("unsupported-trade-parent")
        if trade["state"] == "exact-schema-match" and (trade["value"]["mint"] != mint or trade["value"]["user"] != r["user"] or trade["value"]["is_buy"] is not True):
            raise CaptureError("trade-identity")
        amounts, sol = [], []
        for ins in trade["instructions"]:
            parsed = ins.get("parsed")
            if not isinstance(parsed, dict) or ins.get("stackHeight") != 2:
                continue
            info = parsed.get("info", {})
            if ins.get("programId") == facts["token_program"] and parsed.get("type") == "transferChecked":
                if (info.get("mint") != mint or info.get("source") != r["associated_base_bonding_curve"]
                        or info.get("destination") != r["associated_base_user"] or info.get("authority") != r["bonding_curve"]
                        or type(info["tokenAmount"].get("decimals")) is not int or info["tokenAmount"]["decimals"] != facts["decimals"]):
                    raise CaptureError("token-transfer-mismatch")
                amounts.append(token_units(info["tokenAmount"]["amount"]))
            if (ins.get("programId") == SYSTEM and parsed.get("type") == "transfer"
                    and info.get("source") == r["user"] and info.get("destination") == r["bonding_curve"]):
                if not rpc.integer(info.get("lamports")):
                    raise CaptureError("lamports")
                sol.append(info["lamports"])
        if len(amounts) != 1 or len(sol) != 1 or not amounts[0] or not sol[0]:
            raise CaptureError("purchase-transfers-not-unique")
        transfers.append({"parent_index": trade["parent_index"], "token_base_units": amounts[0],
                          "native_transfer_to_curve_lamports": sol[0], "fees_reconciled": False})
    return {"state": "creation-decoded-trade-schema-mismatch" if any(t["state"] != "exact-schema-match" for t in trades) else "supported-events-decoded-live-blocked",
            "slot": facts["slot"], "decimals": facts["decimals"], "events": public_events,
            "creation_event": {k: create[k] for k in ("virtual_token_reserves", "virtual_sol_reserves", "real_token_reserves", "token_total_supply", "is_mayhem_mode", "is_cashback_enabled", "is_holder_reward", "depth")},
            "creation_mint_to_count": len(mint_to), "creation_minted_base_units": sum(mint_to),
            "event_supply_equals_minted_units": create["token_total_supply"] == sum(mint_to),
            "same_transaction_purchase_transfers": transfers, "creator_identity_verified": False,
            "curve_state_verified": False, "fee_model_verified": False}


def inspect_bundle(report, bundle, layout):
    expected = {n: sha((ROOT / n).read_bytes()) for n in ("rpc_probe.py", "source_probe.py", "capture.py")}
    if (report.get("source_sha256") != expected or report.get("status") != "rpc-facts-reconciled-live-blocked"
            or report.get("paid_collection_enabled") is not False or report.get("credentials_loaded") is not False
            or type(report.get("transactions_sent")) is not int or report["transactions_sent"] != 0):
        raise CaptureError("rpc-report-not-accepted")
    replay = rpc.replay_bundle(bundle)
    if replay != report.get("reconciliation") or replay["status"] != "rpc-facts-reconciled-live-blocked":
        raise CaptureError("rpc-replay-mismatch")
    calls = report.get("rpc_requests")
    if not isinstance(calls, list) or len(calls) != len(bundle["rpc_evidence"]):
        raise CaptureError("request-accounting")
    for i, (call, saved) in enumerate(zip(calls, bundle["rpc_evidence"]), 1):
        if type(call.get("id")) is not int or call["id"] != i or call.get("method") != saved["method"] or call.get("state") != saved["response"]["state"]:
            raise CaptureError("request-accounting")
    cases = []
    for candidate, facts in zip(bundle["candidates"], replay["cases"]):
        tx = next(e["response"]["result"] for e in bundle["rpc_evidence"] if e["method"] == "getTransaction" and e["params"][0] == candidate["signature"])
        try:
            result = inspect_case(candidate, tx, facts, layout)
        except (CaptureError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
            result = {"state": "unsupported-or-inconsistent-event-evidence"}
        cases.append({"case": facts["case"], **result})
    return {"status": "offline-event-inspection-complete-live-blocked", "cases": cases,
            "rpc_replay_matches": True, "network_used": False, "credentials_loaded": False,
            "paid_collection_enabled": False, "curve_reconstruction_accepted": False,
            "deployed_program_version_verified": False, "profitability_evaluated": False,
            "limitations": ["exact IDL decoding is not verification of the deployed binary or economic semantics",
                "unknown event tails are rejected; no partially decoded trade values exported",
                "creation-event reserves are program-reported values, not historical curve account snapshots",
                "parsed purchase transfers exclude fees and rent; they are not total acquisition cost",
                "no-trade result concerns this transaction only; it does not exclude later purchases",
                "only direct SOL create_v2/buy_v2 layouts are supported; other layouts remain unknown",
                "event CPI indexed once; duplicate log emission is not counted as another event"]}


def read_file(path, limit):
    path = Path(os.path.abspath(path))
    if path.resolve() != path or not stat.S_ISREG(path.lstat().st_mode):
        raise CaptureError("input-not-regular")
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise CaptureError("input-cap")
    return raw


def main(argv=None):
    try:
        parser = rpc.Parser(description=__doc__)
        parser.add_argument("--rpc-report", required=True)
        parser.add_argument("--evidence", required=True)
        parser.add_argument("--output", required=True)
        args = parser.parse_args(argv)
        output = Path(args.output)
        if output.exists() or output.is_symlink():
            raise CaptureError("output-exists")
        before = {n: sha((ROOT / n).read_bytes()) for n in SOURCES}
        report_raw = read_file(args.rpc_report, 128 * 1024)
        report = strict_json(report_raw)
        compressed = read_file(args.evidence, 16 * 1024 * 1024)
        if sha(compressed) != report.get("evidence_sha256"):
            raise CaptureError("evidence-checksum")
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as handle:
            raw = handle.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT or sha(raw) != report.get("evidence_decoded_sha256"):
            raise CaptureError("decoded-evidence-checksum-or-size")
        layout = schema()
        result = inspect_bundle(report, strict_json(raw), layout)
        after = {n: sha((ROOT / n).read_bytes()) for n in SOURCES}
        if before != after:
            raise CaptureError("source-changed")
        result.update(source_sha256=after, rpc_report_sha256=sha(report_raw), evidence_sha256=sha(compressed),
                      evidence_decoded_sha256=sha(raw), upstream_idl_commit=layout["upstream_commit"])
        with tempfile.TemporaryDirectory(prefix=".r1-event-", dir=output.parent) as tmp:
            prepared = Path(tmp) / "report.json"
            exclusive_file(prepared, (canonical(result) + "\n").encode())
            os.link(prepared, output, follow_symlinks=False)
        sync_dir(output.parent)
        print("R1 offline event inspection completed; reconstruction and live collection remain blocked.")
        return 0
    except Exception:
        print("R1 event inspection stopped; no reconstruction acceptance is granted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
