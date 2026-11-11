"""Bounded public-RPC deployment metadata probe; no bytecode or fee-config approval."""
import base64
import gzip
import io
from pathlib import Path
import sys

import accounting_inspect as accounting
from capture import CaptureError, canonical, exclusive_file, strict_json, sync_dir
import rpc_probe as rpc

base = accounting.base
ROOT = Path(__file__).resolve().parent
LOADER = "BPFLoaderUpgradeab1e11111111111111111111111"
MAX_REQUESTS = 5
MAX_BUNDLE = 6 * 1024 * 1024
SOURCES = ("deployment_probe.py", *accounting.SOURCES)


def programs():
    layout = base.schema()
    buy = next(x for x in layout["instructions"] if x["name"] == "buy_v2")
    fee = next(x["address"] for x in buy["accounts"] if x["name"] == "fee_program")
    return [layout["program_id"], fee]


class Client(rpc.Client):
    METHODS = {"getGenesisHash", "getMultipleAccounts"}

    def request(self, method, params):
        if method not in self.METHODS:
            raise CaptureError("rpc-method-forbidden")
        if len(self.calls) >= MAX_REQUESTS:
            return {"state": "request-budget-exhausted"}
        return super().request(method, params)


def sample_inputs(report_path, evidence_path):
    report_raw = base.read_file(report_path, 128*1024)
    report = strict_json(report_raw)
    compressed = base.read_file(evidence_path, 16*1024*1024)
    if base.sha(compressed) != report.get("evidence_sha256"):
        raise CaptureError("input-checksum")
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as handle:
        raw = handle.read(base.MAX_INPUT+1)
    if len(raw) > base.MAX_INPUT or base.sha(raw) != report.get("evidence_decoded_sha256"):
        raise CaptureError("decoded-checksum")
    bundle = strict_json(raw)
    review = accounting.inspect(report, bundle)
    if not review["cases"] or any(c["state"] not in ("observed-accounting-consistent-live-blocked", "creation-only-accounting-consistent") for c in review["cases"]):
        raise CaptureError("accounting-not-consistent")
    slots = [c["slot"] for c in report["reconciliation"]["cases"]]
    return slots, {"rpc_report_sha256": base.sha(report_raw), "evidence_sha256": base.sha(compressed),
                   "evidence_decoded_sha256": base.sha(raw)}


def account_bytes(row, length, executable):
    if (not isinstance(row, dict) or row.get("owner") != LOADER or row.get("executable") is not executable
            or not rpc.integer(row.get("lamports")) or row["lamports"] == 0
            or not rpc.integer(row.get("space"), 16*1024*1024)):
        raise CaptureError("account-metadata")
    if (executable and row["space"] != 36) or (not executable and row["space"] < 49):
        raise CaptureError("account-space")
    data = row.get("data")
    if not isinstance(data, list) or len(data) != 2 or data[1] != "base64" or not isinstance(data[0], str) or len(data[0]) > 68:
        raise CaptureError("account-encoding")
    raw = base64.b64decode(data[0], validate=True)
    if len(raw) != length or base64.b64encode(raw).decode() != data[0]:
        raise CaptureError("account-layout")
    return raw


def pointer(row):
    raw = account_bytes(row, 36, True)
    if raw[:4] != (2).to_bytes(4, "little"):
        raise CaptureError("program-tag")
    return base.b58encode(raw[4:]), raw


def metadata(row, context):
    raw = account_bytes(row, 49, False)
    if raw[:4] != (3).to_bytes(4, "little") or raw[12] not in (0, 1) or raw[45:] != b"\x7fELF":
        raise CaptureError("programdata-layout")
    slot = int.from_bytes(raw[4:12], "little")
    if slot > context:
        raise CaptureError("deployment-in-future")
    return {"last_modified_slot": slot, "upgrade_authority_present": raw[12] == 1,
            "allocated_programdata_bytes": row["space"], "header_and_elf_prefix_sha256": base.sha(raw)}


def reconcile(slots, client):
    if not isinstance(slots, list) or not 1 <= len(slots) <= 3 or any(not rpc.integer(s) or s == 0 for s in slots):
        raise CaptureError("sample-slots")
    result = {"status": "deployment-metadata-unavailable", "programs": [], "sample_slots": slots,
              "genesis_verified_before_and_after": False, "metadata_stable_across_reads": False,
              "deployed_program_version_verified": False, "bytecode_verified": False,
              "source_binary_equivalence_verified": False, "programdata_pda_verified": False,
              "historical_fee_config_verified": False, "historical_curve_accounts_verified": False,
              "curve_reconstruction_accepted": False, "paid_collection_enabled": False,
              "profitability_evaluated": False}
    def request(method, params):
        response = client.request(method, params)
        if response.get("state") != "received":
            raise CaptureError("rpc-unavailable")
        return response["result"]
    def read(keys, minimum):
        data = request("getMultipleAccounts", [keys, {"encoding": "base64", "commitment": "finalized",
                       "minContextSlot": minimum, "dataSlice": {"offset": 0, "length": 49}}])
        slot, rows = data["context"]["slot"], data["value"]
        if not rpc.integer(slot) or slot < minimum or not isinstance(rows, list) or len(rows) != len(keys):
            raise CaptureError("account-context")
        return slot, rows
    try:
        if request("getGenesisHash", []) != rpc.GENESIS:
            raise CaptureError("genesis")
        fixed = programs()
        bootstrap_slot, bootstrap = read(fixed, max(slots))
        pointers = [pointer(r)[0] for r in bootstrap]
        if len(set(fixed+pointers+[LOADER, base.SYSTEM])) != 6:
            raise CaptureError("account-alias")
        keys = fixed+pointers
        snapshot_slot, rows = read(keys, bootstrap_slot)
        again_slot, again = read(keys, snapshot_slot)
        observations = []
        for i, label in enumerate(("pump", "pump-fees")):
            first_pointer, first_raw = pointer(rows[i])
            last_pointer, last_raw = pointer(again[i])
            if first_pointer != pointers[i] or last_pointer != pointers[i] or first_raw != last_raw:
                raise CaptureError("pointer-changed")
            first = metadata(rows[i+2], snapshot_slot)
            last = metadata(again[i+2], again_slot)
            if first != last:
                raise CaptureError("metadata-changed")
            observations.append({"program": label, **first,
                "modification_strictly_before_each_sample": [first["last_modified_slot"] < s for s in slots]})
        if request("getGenesisHash", []) != rpc.GENESIS:
            raise CaptureError("genesis-recheck")
        predates = all(all(p["modification_strictly_before_each_sample"]) for p in observations)
        result.update(status="deployment-metadata-predates-sample-live-blocked" if predates else "historical-deployment-window-unresolved",
                      programs=observations, genesis_verified_before_and_after=True, metadata_stable_across_reads=True,
                      bootstrap_context_slot=bootstrap_slot, snapshot_context_slot=snapshot_slot, recheck_context_slot=again_slot)
    except (CaptureError, ValueError, KeyError, TypeError, AttributeError, IndexError, StopIteration, RecursionError):
        pass  # No partial metadata pass or arbitrary provider text.
    result["limitations"] = [
        "current finalized metadata and provider-reported last-modified slots, not historical account snapshots",
        "same-slot modification is unresolved; activation can begin in the following slot",
        "only 49-byte slices are requested; header hashes are not bytecode hashes or source-version attestations",
        "ProgramData pointers are checked for consistency, not independently PDA-derived",
        "covers Pump and Pump Fees only, not their full runtime/dependency chain",
        "mutable fee configuration is not pinned by a program deployment slot",
        "one public RPC provider; no independent cryptographic consensus proof"]
    return result


def replay(bundle, slots, inputs):
    if (type(bundle.get("schema_version")) is not int or bundle["schema_version"] != 1
            or bundle.get("sample_slots") != slots or bundle.get("source_input_sha256") != inputs
            or not isinstance(bundle.get("rpc_evidence"), list) or len(bundle["rpc_evidence"]) > MAX_REQUESTS):
        raise CaptureError("replay-bundle")
    records = bundle["rpc_evidence"]
    class Replay:
        def __init__(self): self.index = 0
        def request(self, method, params):
            if self.index == len(records): return {"state": "request-budget-exhausted"}
            record = records[self.index]
            if record["method"] != method or record["params"] != params:
                raise CaptureError("replay-request")
            self.index += 1
            return record["response"]
    client = Replay()
    result = reconcile(slots, client)
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
        slots, inputs = sample_inputs(args.rpc_report, args.evidence)
        out = Path(args.output_directory)
        out.mkdir(mode=0o700)
        calls = []
        if args.read_public_rpc:
            client = Client()
            result = reconcile(slots, client)
            calls = client.calls
            bundle = {"schema_version": 1, "sample_slots": slots, "source_input_sha256": inputs, "rpc_evidence": client.evidence}
        else:
            compressed = base.read_file(args.replay_evidence, MAX_BUNDLE)
            with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as handle:
                raw = handle.read(MAX_BUNDLE+1)
            if len(raw) > MAX_BUNDLE: raise CaptureError("replay-cap")
            bundle = strict_json(raw)
            result = replay(bundle, slots, inputs)
        if replay(bundle, slots, inputs) != result: raise CaptureError("local-replay")
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
        if retained != evidence or replay(strict_json(gzip.decompress(retained)), slots, inputs) != result:
            raise CaptureError("retained-replay")
        exclusive_file(out/"report.json", (canonical(report)+"\n").encode())
        sync_dir(out)
        sync_dir(out.parent)
        print("R1 deployment metadata probe:", result["status"], "— full R1 remains blocked.")
        return 0
    except Exception:
        print("R1 deployment metadata probe stopped; no acceptance granted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
