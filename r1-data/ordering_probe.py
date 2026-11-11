"""Bounded finalized block-position reconciliation for already saved transactions."""
import gzip
import io
from pathlib import Path
import sys

import deployment_probe as deployment
from capture import CaptureError, canonical, exclusive_file, strict_json, sync_dir
import rpc_probe as rpc

base = deployment.base
ROOT = Path(__file__).resolve().parent
MAX_REQUESTS = 5
MAX_SIGNATURES = 8192
MAX_BUNDLE = deployment.MAX_BUNDLE
SOURCES = ("ordering_probe.py", *deployment.SOURCES)


def samples(report_path, evidence_path):
    slots, inputs = deployment.sample_inputs(report_path, evidence_path)
    compressed = base.read_file(evidence_path, 16*1024*1024)
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as handle:
        raw = handle.read(base.MAX_INPUT+1)
    if (len(raw) > base.MAX_INPUT or base.sha(compressed) != inputs["evidence_sha256"]
            or base.sha(raw) != inputs["evidence_decoded_sha256"]):
        raise CaptureError("input-changed")
    bundle = strict_json(raw)
    report_raw = base.read_file(report_path, 128*1024)
    if base.sha(report_raw) != inputs["rpc_report_sha256"]: raise CaptureError("report-changed")
    prior = base.inspect_bundle(strict_json(report_raw), bundle, base.schema())
    selected = []
    for c, p, slot in zip(bundle["candidates"], prior["cases"], slots):
        tx = next(e["response"]["result"] for e in bundle["rpc_evidence"] if e["method"] == "getTransaction" and e["params"][0] == c["signature"])
        if tx["transaction"]["signatures"][0] != c["signature"]:
            raise CaptureError("primary-signature-required")
        selected.append({"case": p["case"], "slot": slot, "signature": c["signature"],
                         "event_locations": [{k: e[k] for k in ("kind", "parent_index", "inner_index")} for e in p["events"]]})
    return selected, inputs


def block(slot, value):
    allowed = {"blockhash", "previousBlockhash", "parentSlot", "blockHeight", "blockTime", "signatures", "rewards", "numRewardPartitions"}
    if not isinstance(value, dict) or set(value)-allowed or value.get("rewards") not in (None, []):
        raise CaptureError("unavailable-or-unrequested-block-data")
    if (not rpc.identifier(value.get("blockhash"), 32) or not rpc.identifier(value.get("previousBlockhash"), 32)
            or not rpc.integer(value.get("parentSlot")) or value["parentSlot"] >= slot):
        raise CaptureError("block-identity")
    height, timestamp = value.get("blockHeight"), value.get("blockTime")
    if height is not None and not rpc.integer(height): raise CaptureError("block-height")
    partitions = value.get("numRewardPartitions")
    if partitions is not None and not rpc.integer(partitions): raise CaptureError("reward-partitions")
    if timestamp is not None and (type(timestamp) is not int or not -(2**63) <= timestamp < 2**63):
        raise CaptureError("block-time")
    signatures = value.get("signatures")
    if (not isinstance(signatures, list) or not 1 <= len(signatures) <= MAX_SIGNATURES
            or any(not rpc.identifier(s, 64) for s in signatures) or len(set(signatures)) != len(signatures)):
        raise CaptureError("signature-list")
    return {"slot": slot, "blockhash": value["blockhash"], "parent_slot": value["parentSlot"],
            "previous_blockhash": value["previousBlockhash"], "block_height": height, "block_time": timestamp,
            "transaction_count": len(signatures), "ordered_signature_list_sha256": base.sha(canonical(signatures).encode())}, signatures


class Client(rpc.Client):
    METHODS = {"getGenesisHash", "getBlock"}

    def request(self, method, params):
        if method not in self.METHODS: raise CaptureError("rpc-method-forbidden")
        if method == "getGenesisHash" and params != []: raise CaptureError("rpc-params")
        if method == "getBlock" and (not isinstance(params, list) or len(params) != 2
                or not rpc.integer(params[0]) or params[0] == 0
                or params[1] != {"commitment": "finalized", "transactionDetails": "signatures",
                                 "maxSupportedTransactionVersion": 0, "rewards": False}):
            raise CaptureError("rpc-params")
        if len(self.calls) >= MAX_REQUESTS: return {"state": "request-budget-exhausted"}
        result = super().request(method, params)
        if method == "getBlock" and result.get("state") == "received":
            try:
                block(params[0], result["result"])
            except (CaptureError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
                # Do not preserve unrequested full transaction/outcome payloads.
                result = {"state": "block-unavailable-or-unsupported"}
                self.calls[-1]["state"] = result["state"]
                self.evidence[-1]["response"] = result
                self.stopped = True
        return result


def reconcile(selected, client):
    if not isinstance(selected, list) or not 1 <= len(selected) <= 3:
        raise CaptureError("samples")
    for i, sample in enumerate(selected, 1):
        if (type(sample.get("case")) is not int or sample["case"] != i or not rpc.integer(sample.get("slot"))
                or sample["slot"] == 0 or not rpc.identifier(sample.get("signature"), 64)
                or not isinstance(sample.get("event_locations"), list) or not 1 <= len(sample["event_locations"]) <= 2):
            raise CaptureError("sample-identity")
        for event in sample["event_locations"]:
            if (event.get("kind") not in ("CreateEvent", "TradeEvent") or not rpc.integer(event.get("parent_index"))
                    or not rpc.integer(event.get("inner_index"))): raise CaptureError("event-location")
    if len({s["signature"] for s in selected}) != len(selected): raise CaptureError("duplicate-selection")
    result = {"status": "block-ordering-unavailable", "cases": [], "blocks": [], "case_order": [],
              "genesis_verified_before_and_after": False, "finalized_block_positions_reconciled": False,
              "independent_consensus_verified": False, "chain_continuity_verified": False,
              "feed_order_verified": False, "feed_completeness_verified": False, "gap_recovery_verified": False,
              "historical_fee_config_verified": False, "curve_reconstruction_accepted": False,
              "paid_collection_enabled": False, "profitability_evaluated": False}
    def request(method, params):
        response = client.request(method, params)
        if response.get("state") != "received": raise CaptureError("rpc-unavailable")
        return response["result"]
    try:
        if request("getGenesisHash", []) != rpc.GENESIS: raise CaptureError("genesis")
        observed = {}
        for slot in sorted({s["slot"] for s in selected}):
            value = request("getBlock", [slot, {"commitment": "finalized", "transactionDetails": "signatures",
                                               "maxSupportedTransactionVersion": 0, "rewards": False}])
            observed[slot] = block(slot, value)
        if len({b[0]["blockhash"] for b in observed.values()}) != len(observed):
            raise CaptureError("duplicate-blockhash")
        rows, links = [], 0
        for summary, _ in observed.values():
            if summary["parent_slot"] in observed:
                if summary["previous_blockhash"] != observed[summary["parent_slot"]][0]["blockhash"]:
                    raise CaptureError("observed-parent-disagrees")
                links += 1
        for sample in selected:
            summary, signatures = observed[sample["slot"]]
            if sample["signature"] not in signatures:
                result["status"] = "selected-transaction-missing-from-reported-block"
                raise CaptureError("selected-signature-missing")
            index = signatures.index(sample["signature"])
            rows.append({"case": sample["case"], "slot": sample["slot"], "transaction_index": index,
                         "signature_sha256": base.sha(sample["signature"].encode()),
                         "event_positions": [{"kind": e["kind"], "record_order_key": [sample["slot"], index, e["parent_index"], e["inner_index"]]}
                                             for e in sample["event_locations"]]})
        if request("getGenesisHash", []) != rpc.GENESIS: raise CaptureError("genesis-recheck")
        result.update(status="finalized-block-positions-reconciled-live-blocked", cases=rows,
                      blocks=[observed[s][0] for s in sorted(observed)], observed_parent_links_checked=links,
                      case_order=[r["case"] for r in sorted(rows, key=lambda r: (r["slot"], r["transaction_index"]))],
                      genesis_verified_before_and_after=True, finalized_block_positions_reconciled=True)
    except (CaptureError, ValueError, KeyError, TypeError, AttributeError, IndexError, StopIteration, RecursionError):
        pass
    result["limitations"] = ["block signature-list positions from one finalized RPC provider, not cryptographic consensus proof",
        "record keys combine block list position with already saved instruction indices, not wall-clock execution timing",
        "only the selected blocks are read; missing intervening blocks and later trades are not recovered",
        "feed arrival order, subscription gaps and completeness are not established by these block positions",
        "no transaction outcomes, prices, fees, balances or returns requested from getBlock"]
    return result


def replay(bundle, selected, inputs):
    if (type(bundle.get("schema_version")) is not int or bundle["schema_version"] != 1
            or bundle.get("samples") != selected or bundle.get("source_input_sha256") != inputs
            or not isinstance(bundle.get("rpc_evidence"), list) or len(bundle["rpc_evidence"]) > MAX_REQUESTS):
        raise CaptureError("replay-bundle")
    records = bundle["rpc_evidence"]
    for record in records:
        if record["method"] == "getBlock" and record["response"]["state"] == "received":
            block(record["params"][0], record["response"]["result"])
    class Replay:
        def __init__(self): self.index = 0
        def request(self, method, params):
            if self.index == len(records): return {"state": "request-budget-exhausted"}
            record = records[self.index]
            if record["method"] != method or record["params"] != params: raise CaptureError("replay-request")
            self.index += 1
            return record["response"]
    client = Replay()
    result = reconcile(selected, client)
    if client.index != len(records): raise CaptureError("unused-replay-evidence")
    return result


def main(argv=None):
    try:
        parser = rpc.Parser(description=__doc__)
        for name in ("rpc-report", "evidence", "output-directory"):
            parser.add_argument("--"+name, required=True)
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--read-public-rpc", action="store_true")
        mode.add_argument("--replay-evidence")
        args = parser.parse_args(argv)
        pins = {n: base.sha((ROOT/n).read_bytes()) for n in SOURCES}
        selected, inputs = samples(args.rpc_report, args.evidence)
        out = Path(args.output_directory)
        out.mkdir(mode=0o700)
        calls = []
        if args.read_public_rpc:
            client = Client()
            result = reconcile(selected, client)
            calls = client.calls
            bundle = {"schema_version": 1, "samples": selected, "source_input_sha256": inputs, "rpc_evidence": client.evidence}
        else:
            compressed = base.read_file(args.replay_evidence, MAX_BUNDLE)
            with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as handle:
                raw = handle.read(MAX_BUNDLE+1)
            if len(raw) > MAX_BUNDLE: raise CaptureError("replay-cap")
            bundle = strict_json(raw)
            result = replay(bundle, selected, inputs)
        if replay(bundle, selected, inputs) != result: raise CaptureError("local-replay")
        if pins != {n: base.sha((ROOT/n).read_bytes()) for n in SOURCES}: raise CaptureError("source-changed")
        raw = canonical(bundle).encode()
        if len(raw) > MAX_BUNDLE: raise CaptureError("evidence-cap")
        evidence = gzip.compress(raw, mtime=0)
        report = {"schema_version": 1, "status": result["status"], "reconciliation": result,
                  "endpoint": rpc.ENDPOINT, "rpc_requests": calls, "network_used": bool(calls),
                  "credentials_loaded": False, "paid_collection_enabled": False, "transactions_sent": 0,
                  "source_sha256": pins, "source_input_sha256": inputs, "local_replay_verified": True,
                  "evidence_sha256": base.sha(evidence), "evidence_decoded_sha256": base.sha(raw),
                  "evidence_file": "evidence.json.gz"}
        exclusive_file(out/"evidence.json.gz", evidence)
        retained = (out/"evidence.json.gz").read_bytes()
        if retained != evidence or replay(strict_json(gzip.decompress(retained)), selected, inputs) != result:
            raise CaptureError("retained-replay")
        exclusive_file(out/"report.json", (canonical(report)+"\n").encode())
        sync_dir(out)
        sync_dir(out.parent)
        print("R1 block ordering probe:", result["status"], "— full R1 remains blocked.")
        return 0
    except Exception:
        print("R1 block ordering probe stopped; no acceptance granted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
