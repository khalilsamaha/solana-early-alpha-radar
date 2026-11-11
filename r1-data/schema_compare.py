"""Offline comparison with a documented newer TradeEvent layout; diagnostic only.

The Kali-accepted default inspector and its schema remain unchanged. This tool
does not select a production schema or establish historical deployment semantics.
"""
import copy
import gzip
import io
import os
from pathlib import Path
import sys
import tempfile

import event_inspect as base
from capture import CaptureError, canonical, exclusive_file, strict_json, sync_dir
from rpc_probe import Parser

ROOT = Path(__file__).resolve().parent
PROFILE = "trade_profile_0_5_0.json"
PROFILE_SHA256 = "500612a20b6829dfdd3475290af27ed8d6450df99adb27ea366fed2669fe214b"
SOURCES = ("schema_compare.py", PROFILE, *base.SOURCES)


def candidate_layout():
    raw = (ROOT / PROFILE).read_bytes()
    if base.sha(raw) != PROFILE_SHA256:
        raise CaptureError("profile-pin")
    profile = strict_json(raw)
    layout = copy.deepcopy(base.schema())
    event_type = next(t for t in layout["types"] if t["name"] == "TradeEvent")
    fields = profile["event"]["type"]["fields"]
    if (profile["base_schema_sha256"] != base.SCHEMA_SHA256 or profile["event"]["name"] != "TradeEvent"
            or fields[:-1] != event_type["type"]["fields"] or fields[-1] != {"name": "quote_transfer_fee", "type": "u64"}):
        raise CaptureError("profile-definition")
    event_type["type"]["fields"] = fields
    return layout, profile


def encode_event(values, definition, layout):
    """Round-trip all declared bytes, including vectors and nonzero extension."""
    types = {t["name"]: t["type"]["fields"] for t in layout["types"]}
    def encode(kind, value):
        if kind == "pubkey": return base.b58decode(value)
        if kind == "string":
            raw = value.encode("utf-8"); return len(raw).to_bytes(4, "little") + raw
        if isinstance(kind, str):
            return int(value).to_bytes({"bool": 1, "u8": 1, "u16": 2, "u64": 8, "i64": 8}[kind], "little", signed=kind == "i64")
        if "vec" in kind:
            return len(value).to_bytes(4, "little") + b"".join(encode(kind["vec"], item) for item in value)
        return fields(types[kind["defined"]["name"]], value)
    def fields(spec, value):
        return b"".join(encode(f["type"], value[f["name"]]) for f in spec)
    return bytes(definition["discriminator"]) + fields(types[definition["name"]], values)


def compare(report, bundle):
    baseline = base.inspect_bundle(report, bundle, base.schema())
    layout, profile = candidate_layout()
    definition = next(x for x in layout["events"] if x["name"] == "TradeEvent")
    result = {"schema_version": 1, "status": "offline-schema-comparison-complete-live-blocked", "cases": [],
              "profile": profile["profile"], "profile_sha256": PROFILE_SHA256,
              "default_inspector_unchanged": True, "network_used": False, "credentials_loaded": False,
              "paid_collection_enabled": False, "transactions_sent": 0, "deployed_program_version_verified": False,
              "archive_checksum_verified": False, "fee_model_verified": False,
              "curve_reconstruction_accepted": False, "ix_name_mapping_verified": False,
              "profitability_evaluated": False}
    for candidate, prior in zip(bundle["candidates"], baseline["cases"]):
        item = {"case": prior["case"], "baseline_state": prior["state"], "trade_events": []}
        result["cases"].append(item)
        if prior["state"] == "unsupported-or-inconsistent-event-evidence":
            item["state"] = "baseline-unsupported"
            continue
        tx = next(x["response"]["result"] for x in bundle["rpc_evidence"] if x["method"] == "getTransaction" and x["params"][0] == candidate["signature"])
        for event in [x for x in prior["events"] if x["kind"] == "TradeEvent"]:
            record = {"parent_index": event["parent_index"], "inner_index": event["inner_index"],
                      "payload_sha256": event["payload_sha256"], "payload_bytes": event["payload_bytes"],
                      "baseline_state": event["state"], "candidate_state": "unsupported"}
            item["trade_events"].append(record)
            try:
                group = next(g for g in tx["meta"]["innerInstructions"] if g["index"] == event["parent_index"])
                raw = base.b58decode(group["instructions"][event["inner_index"]]["data"])[8:]
                if base.sha(raw) != event["payload_sha256"]:
                    raise CaptureError("event-identity")
                values = base.decode_event(raw, definition, layout)
                parent = tx["transaction"]["message"]["instructions"][event["parent_index"]]
                transfer = next(t for t in prior["same_transaction_purchase_transfers"] if t["parent_index"] == event["parent_index"])
                if (values["mint"] != candidate["mint"] or values["user"] != parent["accounts"][13]
                        or values["is_buy"] is not True or values["token_amount"] != transfer["token_base_units"]
                        or values["sol_amount"] != transfer["native_transfer_to_curve_lamports"]
                        or values["quote_mint"] != base.SYSTEM or values["quote_amount"] != values["sol_amount"]):
                    raise CaptureError("candidate-identity-or-transfer")
                if encode_event(values, definition, layout) != raw:
                    raise CaptureError("roundtrip")
                record.update(candidate_state="exact-layout-and-transfer-match-diagnostic-only", bytes_consumed=len(raw),
                              reencoded_bytes_match=True, quote_transfer_fee_reported=values["quote_transfer_fee"],
                              parent_instruction="buy_v2", event_ix_name_reported=values["ix_name"])
            except (CaptureError, ValueError, KeyError, TypeError, AttributeError, StopIteration, RecursionError):
                pass
        item["state"] = "no-trade-in-this-transaction" if not item["trade_events"] else "comparison-recorded"
    result["limitations"] = ["new profile is an extracted documentation definition, not a checksum-verified crate archive",
        "exact byte and transfer agreement does not attest deployed program version or activation range",
        "reported ix_name is preserved literally, not normalized to the parent instruction name",
        "fee/reserve semantics and reconstruction remain unaccepted; default strict decoder is unchanged"]
    return result


def main(argv=None):
    try:
        parser = Parser(description=__doc__)
        parser.add_argument("--rpc-report", required=True)
        parser.add_argument("--evidence", required=True)
        parser.add_argument("--output", required=True)
        args = parser.parse_args(argv)
        output = Path(args.output)
        if output.exists() or output.is_symlink(): raise CaptureError("output-exists")
        pins = {n: base.sha((ROOT/n).read_bytes()) for n in SOURCES}
        report_raw = base.read_file(args.rpc_report, 128 * 1024)
        report = strict_json(report_raw)
        compressed = base.read_file(args.evidence, 16 * 1024 * 1024)
        if base.sha(compressed) != report.get("evidence_sha256"): raise CaptureError("checksum")
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as handle:
            raw = handle.read(base.MAX_INPUT + 1)
        if len(raw) > base.MAX_INPUT or base.sha(raw) != report.get("evidence_decoded_sha256"):
            raise CaptureError("decoded-checksum-or-cap")
        result = compare(report, strict_json(raw))
        if pins != {n: base.sha((ROOT/n).read_bytes()) for n in SOURCES}: raise CaptureError("source-changed")
        result.update(source_sha256=pins, rpc_report_sha256=base.sha(report_raw),
                      evidence_sha256=base.sha(compressed), evidence_decoded_sha256=base.sha(raw))
        with tempfile.TemporaryDirectory(prefix=".r1-schema-", dir=output.parent) as tmp:
            prepared = Path(tmp)/"report.json"
            exclusive_file(prepared, (canonical(result)+"\n").encode())
            os.link(prepared, output, follow_symlinks=False)
        sync_dir(output.parent)
        print("R1 schema comparison recorded; deployment and economic acceptance remain blocked.")
        return 0
    except Exception:
        print("R1 schema comparison stopped; no acceptance granted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
