import contextlib
import copy
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import event_inspect as e
import rpc_probe as r
from test_rpc_probe import CANDIDATE, SIG, STATUS, Opener, account


LAYOUT = e.schema()
PUMP = LAYOUT["program_id"]


def key(n):
    return e.b58encode(n.to_bytes(32, "big"))


def defaults(name):
    fields = next(t["type"]["fields"] for t in LAYOUT["types"] if t["name"] == name)
    return {f["name"]: ("fixture" if f["type"] == "string" else key(2) if f["type"] == "pubkey" else False if f["type"] == "bool" else [] if isinstance(f["type"], dict) else 0) for f in fields}


def encode(name, values):
    fields = next(t["type"]["fields"] for t in LAYOUT["types"] if t["name"] == name)
    def value(kind, item):
        if kind == "pubkey": return e.b58decode(item)
        if kind == "string":
            raw = item.encode(); return len(raw).to_bytes(4, "little") + raw
        if isinstance(kind, str):
            return int(item).to_bytes({"u8": 1, "u16": 2, "u64": 8, "i64": 8, "bool": 1}[kind], "little", signed=kind == "i64")
        return len(item).to_bytes(4, "little") + b"".join(e.b58decode(x["address"]) + x["share_bps"].to_bytes(2, "little") for x in item)
    event = next(x for x in LAYOUT["events"] if x["name"] == name)
    return bytes(event["discriminator"]) + b"".join(value(f["type"], values[f["name"]]) for f in fields)


def fixture(*, trade=True, tail=b"", mayhem=False):
    create_def = next(x for x in LAYOUT["instructions"] if x["name"] == "create_v2")
    buy_def = next(x for x in LAYOUT["instructions"] if x["name"] == "buy_v2")
    cr = {a["name"]: a.get("address", key(100+i)) for i, a in enumerate(create_def["accounts"])}
    cr.update(mint=CANDIDATE["mint"], program=PUMP)
    br = {a["name"]: a.get("address", key(200+i)) for i, a in enumerate(buy_def["accounts"])}
    br.update(base_mint=cr["mint"], quote_mint=e.WSOL, base_token_program=r.TOKEN_2022, quote_token_program=r.TOKEN,
              bonding_curve=cr["bonding_curve"], associated_base_bonding_curve=cr["associated_bonding_curve"],
              user=cr["user"], event_authority=cr["event_authority"], program=PUMP)
    create = defaults("CreateEvent")
    create.update(mint=cr["mint"], bonding_curve=cr["bonding_curve"], user=cr["user"], creator=cr["user"],
                  token_program=r.TOKEN_2022, quote_mint=e.SYSTEM, is_mayhem_mode=mayhem, token_total_supply=1000)
    buy = defaults("TradeEvent"); buy.update(mint=cr["mint"], user=cr["user"], is_buy=True)
    def parent(d, roles):
        return {"programId": PUMP, "stackHeight": 1, "accounts": [roles[a["name"]] for a in d["accounts"]],
                "data": e.b58encode(bytes(d["discriminator"]) + b"synthetic-args")}
    def event(name, vals, suffix=b""):
        return {"programId": PUMP, "stackHeight": 2, "accounts": [cr["event_authority"]],
                "data": e.b58encode(e.EVENT_TAG + encode(name, vals) + suffix)}
    def parsed(program, kind, info):
        return {"programId": program, "stackHeight": 2, "parsed": {"type": kind, "info": info}}
    cins = [parsed(r.TOKEN_2022, "initializeMint2", {"mint": cr["mint"], "decimals": 6}),
            parsed(r.TOKEN_2022, "mintTo", {"mint": cr["mint"], "amount": "1000"})]
    if mayhem: cins.append(copy.deepcopy(cins[-1]))
    cins.append(event("CreateEvent", create))
    top = [parent(create_def, cr)]
    groups = [{"index": 0, "instructions": cins}]
    if trade:
        top.append(parent(buy_def, br))
        groups.append({"index": 1, "instructions": [
            parsed(r.TOKEN_2022, "transferChecked", {"mint": cr["mint"], "source": br["associated_base_bonding_curve"],
                "destination": br["associated_base_user"], "authority": br["bonding_curve"], "tokenAmount": {"amount": "123", "decimals": 6}}),
            parsed(e.SYSTEM, "transfer", {"source": br["user"], "destination": br["bonding_curve"], "lamports": 456}),
            event("TradeEvent", buy, tail)]})
    keys = list(dict.fromkeys([*cr.values(), *br.values()]))
    tx = {"slot": 100, "version": 0, "meta": {"err": None, "innerInstructions": groups, "logMessages": []},
          "transaction": {"signatures": [SIG, "1" * 63 + "3"], "message": {
              "accountKeys": [{"pubkey": k, "signer": k in {cr["mint"], cr["user"]}} for k in keys], "instructions": top}}}
    return tx


def accepted(tx):
    opener = Opener()
    def response(p):
        data = {"getGenesisHash": r.GENESIS, "getSignatureStatuses": {"context": {"slot": 200}, "value": [STATUS]},
                "getTransaction": tx, "getAccountInfo": account(r.TOKEN_2022)}[p["method"]]
        return io.BytesIO(json.dumps({"jsonrpc": "2.0", "id": p["id"], "result": data}).encode())
    opener.override = response
    client = r.Client(opener, pause=lambda _: None)
    result = r.reconcile([CANDIDATE], client)
    assert result["status"] == "rpc-facts-reconciled-live-blocked"
    bundle = {"schema_version": 1, "candidates": [CANDIDATE], "rpc_evidence": client.evidence}
    raw = e.canonical(bundle).encode(); compressed = gzip.compress(raw, mtime=0)
    report = {"status": result["status"], "source_sha256": {n: e.sha((e.ROOT/n).read_bytes()) for n in ("rpc_probe.py", "source_probe.py", "capture.py")},
              "reconciliation": result, "rpc_requests": client.calls, "paid_collection_enabled": False,
              "credentials_loaded": False, "transactions_sent": 0, "evidence_sha256": e.sha(compressed), "evidence_decoded_sha256": e.sha(raw)}
    return report, bundle, compressed


class DecodeTests(unittest.TestCase):
    def decode(self, name, raw):
        return e.decode_event(raw, next(x for x in LAYOUT["events"] if x["name"] == name), LAYOUT)
    def test_exact_create_schema_roundtrip(self):
        obj = defaults("CreateEvent")
        self.assertEqual(self.decode("CreateEvent", encode("CreateEvent", obj)), obj)
    def test_full_trade_schema_including_shareholders(self):
        obj = defaults("TradeEvent"); obj["shareholders"] = [{"address": key(999), "share_bps": 10000}]
        self.assertEqual(self.decode("TradeEvent", encode("TradeEvent", obj)), obj)
    def test_all_truncation_positions_rejected(self):
        raw = encode("CreateEvent", defaults("CreateEvent"))
        for end in range(len(raw)):
            with self.assertRaises(e.CaptureError): self.decode("CreateEvent", raw[:end])
    def test_trailing_zero_bytes_are_not_tolerated(self):
        with self.assertRaises(e.SchemaMismatch) as ctx:
            self.decode("TradeEvent", encode("TradeEvent", defaults("TradeEvent")) + b"\0" * 8)
        self.assertEqual(ctx.exception.remaining, 8)
    def test_wrong_discriminator_rejected(self):
        raw = encode("CreateEvent", defaults("CreateEvent"))
        with self.assertRaises(e.CaptureError): self.decode("CreateEvent", b"x" + raw[1:])
    def test_bool_must_be_zero_or_one(self):
        obj = defaults("TradeEvent"); obj["is_buy"] = 2
        with self.assertRaises(e.CaptureError): self.decode("TradeEvent", encode("TradeEvent", obj))
    def test_string_and_vector_caps(self):
        obj = defaults("CreateEvent"); obj["name"] = "x" * 513
        with self.assertRaises(e.CaptureError): self.decode("CreateEvent", encode("CreateEvent", obj))
        obj = defaults("TradeEvent"); obj["shareholders"] = [{"address": key(2), "share_bps": 1}] * 17
        with self.assertRaises(e.CaptureError): self.decode("TradeEvent", encode("TradeEvent", obj))
    def test_large_integers_remain_exact(self):
        obj = defaults("TradeEvent"); obj.update(token_amount=2**64-1, timestamp=-(2**63))
        self.assertEqual(self.decode("TradeEvent", encode("TradeEvent", obj)), obj)
    def test_base58_bounds_and_leading_zeroes(self):
        for raw in [b"\0" * 32, b"\0" * 31 + b"\1", b"\xff" * 32]:
            self.assertEqual(e.b58decode(e.b58encode(raw)), raw)
        for bad in ["", "0", "1" * 6001]:
            with self.assertRaises(e.CaptureError): e.b58decode(bad)


class InspectTests(unittest.TestCase):
    def inspect(self, tx):
        report, bundle, _ = accepted(tx)
        return e.inspect_bundle(report, bundle, LAYOUT)["cases"][0]
    def test_purchase_transfers_are_separate_from_schema_mismatch(self):
        result = self.inspect(fixture(tail=b"\0" * 8))
        self.assertEqual(result["state"], "creation-decoded-trade-schema-mismatch")
        self.assertEqual(result["events"][1]["unconsumed_bytes"], 8)
        self.assertNotIn("value", result["events"][1])
        self.assertEqual(result["same_transaction_purchase_transfers"][0]["token_base_units"], 123)
        self.assertFalse(result["curve_state_verified"])
    def test_no_trade_claim_is_transaction_scoped(self):
        result = self.inspect(fixture(trade=False))
        self.assertEqual(result["same_transaction_purchase_transfers"], [])
        self.assertFalse(result["fee_model_verified"])
    def test_mayhem_supply_is_observed_not_assumed(self):
        result = self.inspect(fixture(mayhem=True))
        self.assertEqual(result["creation_minted_base_units"], 2000)
        self.assertFalse(result["event_supply_equals_minted_units"])
        self.assertTrue(result["creation_event"]["is_mayhem_mode"])
    def test_wrong_event_tag_program_authority_or_stack_cannot_pass(self):
        for field, value in [("programId", key(9)), ("stackHeight", 3), ("accounts", [key(9)]), ("data", e.b58encode(b"x" * 20))]:
            tx = fixture(); tx["meta"]["innerInstructions"][0]["instructions"][-1][field] = value
            self.assertEqual(self.inspect(tx)["state"], "unsupported-or-inconsistent-event-evidence")
    def test_missing_or_duplicate_trade_event_does_not_mean_no_trade(self):
        for duplicate in [False, True]:
            tx = fixture(); ins = tx["meta"]["innerInstructions"][1]["instructions"]
            if duplicate: ins.append(copy.deepcopy(ins[-1]))
            else: ins.pop()
            self.assertEqual(self.inspect(tx)["state"], "unsupported-or-inconsistent-event-evidence")
    def test_quote_and_parent_instruction_mismatch_rejected(self):
        for change in ["quote", "instruction", "accounts", "bool-height"]:
            tx = fixture(); parent = tx["transaction"]["message"]["instructions"][1]
            if change == "quote": parent["accounts"][2] = key(100)
            elif change == "instruction": parent["data"] = e.b58encode(b"x" * 24)
            elif change == "accounts": parent["accounts"].append(key(100))
            else: parent["stackHeight"] = True
            self.assertEqual(self.inspect(tx)["state"], "unsupported-or-inconsistent-event-evidence")
    def test_transfer_identity_amount_or_decimals_mismatch_rejected(self):
        for field, val in [("source", key(9)), ("authority", key(9)), ("tokenAmount", {"amount": "1.2", "decimals": 6}), ("tokenAmount", {"amount": "123", "decimals": True})]:
            tx = fixture(); tx["meta"]["innerInstructions"][1]["instructions"][0]["parsed"]["info"][field] = val
            self.assertEqual(self.inspect(tx)["state"], "unsupported-or-inconsistent-event-evidence")
    def test_duplicate_transfers_rejected(self):
        tx = fixture(); ins = tx["meta"]["innerInstructions"][1]["instructions"]; ins.append(copy.deepcopy(ins[0]))
        self.assertEqual(self.inspect(tx)["state"], "unsupported-or-inconsistent-event-evidence")
    def test_logs_do_not_duplicate_cpi_events(self):
        tx = fixture(); baseline = self.inspect(tx)
        tx["meta"]["logMessages"] = ["Program data: FAKE"] * 10
        self.assertEqual(self.inspect(tx), baseline)
    def test_source_pins_replay_and_request_accounting_required(self):
        original, bundle, _ = accepted(fixture())
        for kind in ["pin", "replay", "requests"]:
            report = copy.deepcopy(original)
            if kind == "pin": report["source_sha256"]["rpc_probe.py"] = "bad"
            elif kind == "replay": report["reconciliation"]["cases"][0]["decimals"] = 9
            else: report["rpc_requests"][0]["method"] = "getAccountInfo"
            with self.assertRaises(e.CaptureError): e.inspect_bundle(report, bundle, LAYOUT)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        report, _, compressed = accepted(fixture(tail=b"\0" * 8))
        self.report = self.root / "report.json"; self.report.write_text(json.dumps(report))
        self.bundle = self.root / "evidence.json.gz"; self.bundle.write_bytes(compressed)
        self.output = self.root / "output.json"
    def tearDown(self): self.temp.cleanup()
    def call(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return e.main(["--rpc-report", str(self.report), "--evidence", str(self.bundle), "--output", str(self.output)])
    def test_cli_is_offline_private_and_preserves_inputs(self):
        before = [p.read_bytes() for p in [self.report, self.bundle]]
        self.assertEqual(self.call(), 0)
        result = json.loads(self.output.read_text())
        self.assertFalse(result["network_used"])
        self.assertFalse(result["curve_reconstruction_accepted"])
        self.assertEqual(result["evidence_sha256"], e.sha(self.bundle.read_bytes()))
        self.assertEqual(before, [p.read_bytes() for p in [self.report, self.bundle]])
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(CANDIDATE["mint"], self.output.read_text())
    def test_checksum_failure_creates_no_report(self):
        self.bundle.write_bytes(self.bundle.read_bytes() + b"x")
        self.assertEqual(self.call(), 1); self.assertFalse(self.output.exists())
    def test_decompression_cap_stops_before_json_parsing(self):
        with patch.object(e, "MAX_INPUT", 32):
            self.assertEqual(self.call(), 1)
        self.assertFalse(self.output.exists())
    def test_existing_output_is_never_replaced(self):
        self.output.write_text("preserve")
        self.assertEqual(self.call(), 1); self.assertEqual(self.output.read_text(), "preserve")
    def test_schema_pin_mismatch_stops(self):
        with patch.object(e, "SCHEMA_SHA256", "bad"):
            self.assertEqual(self.call(), 1)
        self.assertFalse(self.output.exists())
    def test_symlink_and_bounded_read_refused(self):
        link = self.root / "link"; link.symlink_to(self.report)
        with self.assertRaises(e.CaptureError): e.read_file(link, 100000)
        with self.assertRaises(e.CaptureError): e.read_file(self.report, 10)
