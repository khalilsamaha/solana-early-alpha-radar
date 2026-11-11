import contextlib
import copy
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import ordering_probe as o
from test_accounting_inspect import fixture
from test_event_inspect import accepted, key

INPUTS = {"rpc_report_sha256": "a"*64, "evidence_sha256": "b"*64, "evidence_decoded_sha256": "c"*64}


def sig(n):
    return o.base.b58encode(n.to_bytes(64, "big"))


def selection(slots=(110, 100, 120)):
    return [{"case": i, "slot": slot, "signature": sig(i),
             "event_locations": [{"kind": "CreateEvent", "parent_index": 2, "inner_index": 4}]}
            for i, slot in enumerate(slots, 1)]


class Opener:
    def __init__(self, selected, change=None):
        self.selected = selected
        self.change = change
        self.requests = []

    def open(self, request, timeout):
        payload = json.loads(request.data)
        self.requests.append(payload)
        if payload["method"] == "getGenesisHash":
            value = o.rpc.GENESIS
        else:
            slot = payload["params"][0]
            value = {"blockhash": key(slot), "previousBlockhash": key(slot-1), "parentSlot": slot-1,
                     "blockHeight": slot-10, "blockTime": None,
                     "signatures": [sig(999)] + [s["signature"] for s in reversed(self.selected) if s["slot"] == slot]}
        if self.change:
            value = self.change(payload, value)
        return io.BytesIO(json.dumps({"jsonrpc": "2.0", "id": payload["id"], "result": value}).encode())


class OrderingTests(unittest.TestCase):
    def run_probe(self, selected=None, change=None):
        selected = selection() if selected is None else selected
        opener = Opener(selected, change)
        client = o.Client(opener, pause=lambda _: None)
        return o.reconcile(selected, client), client, opener

    def test_five_bounded_reads_and_record_keys_without_broader_acceptance(self):
        result, client, opener = self.run_probe()
        self.assertEqual(result["status"], "finalized-block-positions-reconciled-live-blocked")
        self.assertEqual(len(client.calls), 5)
        self.assertEqual([p["method"] for p in opener.requests], ["getGenesisHash"]+["getBlock"]*3+["getGenesisHash"])
        self.assertEqual([p["params"][0] for p in opener.requests[1:4]], [100, 110, 120])
        for p in opener.requests[1:4]:
            self.assertEqual(p["params"][1], {"commitment": "finalized", "transactionDetails": "signatures",
                                              "maxSupportedTransactionVersion": 0, "rewards": False})
        self.assertEqual(result["case_order"], [2, 1, 3])
        self.assertEqual(result["cases"][0]["event_positions"][0]["record_order_key"], [110, 1, 2, 4])
        for flag in ("independent_consensus_verified", "chain_continuity_verified", "feed_order_verified",
                     "feed_completeness_verified", "gap_recovery_verified", "historical_fee_config_verified",
                     "curve_reconstruction_accepted", "paid_collection_enabled", "profitability_evaluated"):
            self.assertIs(result[flag], False)

    def test_same_block_queried_once_positions_determine_order(self):
        result, client, _ = self.run_probe(selection((100, 100, 100)))
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(result["case_order"], [3, 2, 1])
        self.assertEqual([c["transaction_index"] for c in result["cases"]], [3, 2, 1])

    def test_unavailable_duplicate_invalid_and_oversized_signature_lists(self):
        for signatures in ([], [sig(1), sig(1)], ["invalid"], [True], [sig(1)]*(o.MAX_SIGNATURES+1)):
            def change(p, v):
                if p["method"] == "getBlock": v["signatures"] = signatures
                return v
            result, client, _ = self.run_probe(change=change)
            self.assertEqual(result["cases"], [])
            self.assertEqual(len(client.calls), 2)
            self.assertEqual(client.evidence[-1]["response"], {"state": "block-unavailable-or-unsupported"})
        result, _, _ = self.run_probe(change=lambda p,v: None if p["method"] == "getBlock" else v)
        self.assertFalse(result["finalized_block_positions_reconciled"])

    def test_block_identity_numeric_metadata_and_unrequested_payload_rejected(self):
        for field, value in (("parentSlot", True), ("parentSlot", 100), ("parentSlot", -1),
                             ("blockhash", "bad"), ("previousBlockhash", False), ("blockHeight", True),
                             ("blockTime", 2**63), ("blockTime", True), ("numRewardPartitions", -1),
                             ("rewards", [{"SECRET": "payload"}]), ("transactions", [{"SECRET": "payload"}])):
            def change(p, v):
                if p["method"] == "getBlock": v[field] = value
                return v
            result, client, _ = self.run_probe(change=change)
            self.assertEqual(result["status"], "block-ordering-unavailable")
            self.assertNotIn("SECRET", json.dumps([result, client.evidence, client.calls]))
            self.assertTrue(client.stopped)

    def test_missing_selected_signature_has_distinct_status_without_partial_pass(self):
        def change(p, v):
            if p["method"] == "getBlock" and p["params"][0] == 110: v["signatures"] = [sig(999)]
            return v
        result, client, _ = self.run_probe(change=change)
        self.assertEqual(result["status"], "selected-transaction-missing-from-reported-block")
        self.assertEqual(result["cases"], [])
        self.assertEqual(len(client.calls), 4)
        self.assertFalse(result["finalized_block_positions_reconciled"])

    def test_wrong_genesis_at_either_boundary_never_exports_positions(self):
        for at in (1, 5):
            result, client, _ = self.run_probe(change=lambda p,v: "wrong-chain" if p["id"] == at else v)
            self.assertEqual(result["cases"], [])
            self.assertEqual(len(client.calls), at)
            self.assertFalse(result["genesis_verified_before_and_after"])

    def test_parent_link_checks_are_limited_and_duplicate_blockhash_rejected(self):
        selected = selection((100, 101, 102))
        result, _, _ = self.run_probe(selected)
        self.assertEqual(result["observed_parent_links_checked"], 2)
        self.assertFalse(result["chain_continuity_verified"])
        for field in ("previousBlockhash", "blockhash"):
            def change(p, v):
                if p["method"] == "getBlock" and p["params"][0] == 101: v[field] = key(102)
                return v
            self.assertEqual(self.run_probe(selected, change)[0]["cases"], [])

    def test_method_params_budget_and_expired_deadline_prevent_extra_traffic(self):
        _, client, opener = self.run_probe()
        self.assertEqual(client.request("getGenesisHash", [])["state"], "request-budget-exhausted")
        for method, params in (("sendTransaction", []), ("getGenesisHash", [1]),
                               ("getBlock", [100, {"transactionDetails": "full"}])):
            with self.assertRaises(o.CaptureError): client.request(method, params)
        self.assertEqual(len(opener.requests), 5)
        client = o.Client(Opener(selection()), clock=lambda: 0, pause=lambda _: None)
        client.deadline = 0
        self.assertEqual(o.reconcile(selection(), client)["cases"], [])
        self.assertEqual(client.calls, [])
        for selected in ([], selection((True,)), selection((0,)), selection((2**64,)), selection((1,2,3,4))):
            with self.assertRaises(o.CaptureError): o.reconcile(selected, client)
        duplicate = selection(); duplicate[1]["signature"] = duplicate[0]["signature"]
        with self.assertRaises(o.CaptureError): o.reconcile(duplicate, client)

    def test_transport_failure_stops_without_retry_or_provider_text(self):
        def change(p, v):
            if p["method"] == "getBlock": raise HTTPError("https://invalid/", 429, "SECRET", None, io.BytesIO(b"SECRET"))
            return v
        result, client, _ = self.run_probe(change=change)
        self.assertEqual(len(client.calls), 2)
        self.assertFalse(result["finalized_block_positions_reconciled"])
        self.assertNotIn("SECRET", json.dumps([result, client.evidence, client.calls]))

    def test_replay_binds_inputs_selected_samples_requests_and_all_records(self):
        result, client, _ = self.run_probe()
        original = {"schema_version": 1, "samples": selection(), "source_input_sha256": INPUTS, "rpc_evidence": client.evidence}
        self.assertEqual(o.replay(original, selection(), INPUTS), result)
        for kind in ("input", "slot", "method", "params", "extra", "unrequested"):
            bundle = copy.deepcopy(original)
            if kind == "input": bundle["source_input_sha256"]["rpc_report_sha256"] = "bad"
            elif kind == "slot": bundle["samples"][0]["slot"] += 1
            elif kind == "method": bundle["rpc_evidence"][1]["method"] = "getTransaction"
            elif kind == "params": bundle["rpc_evidence"][1]["params"][1]["commitment"] = "processed"
            elif kind == "extra": bundle["rpc_evidence"].append(copy.deepcopy(bundle["rpc_evidence"][-1]))
            else: bundle["rpc_evidence"][1]["response"]["result"]["transactions"] = []
            with self.assertRaises(o.CaptureError): o.replay(bundle, selection(), INPUTS)


class OrderingCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        report, _, compressed = accepted(fixture())
        self.report = self.root/"input.json"; self.report.write_text(json.dumps(report))
        self.evidence = self.root/"input.json.gz"; self.evidence.write_bytes(compressed)
        self.out = self.root/"out"
        self.selected, _ = o.samples(self.report, self.evidence)
        self.client = o.Client(Opener(self.selected), pause=lambda _: None)

    def tearDown(self): self.temp.cleanup()

    def call(self, mode=("--read-public-rpc",)):
        self.messages = io.StringIO()
        with patch.object(o, "Client", return_value=self.client), patch("socket.socket", side_effect=AssertionError("network forbidden")), contextlib.redirect_stdout(self.messages), contextlib.redirect_stderr(self.messages):
            return o.main(["--rpc-report", str(self.report), "--evidence", str(self.evidence), "--output-directory", str(self.out), *mode])

    def test_private_capture_replay_and_original_input_preservation(self):
        before = [p.read_bytes() for p in (self.report, self.evidence)]
        self.assertEqual(self.call(), 0)
        report = json.loads((self.out/"report.json").read_text())
        self.assertEqual(report["status"], "finalized-block-positions-reconciled-live-blocked")
        self.assertEqual(len(report["rpc_requests"]), 3)
        self.assertEqual(len(report["source_sha256"]), 10)
        for p in (self.out/"report.json", self.out/"evidence.json.gz"): self.assertEqual(p.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o700)
        saved = self.out/"evidence.json.gz"; self.out = self.root/"replayed"
        self.assertEqual(self.call(("--replay-evidence", str(saved))), 0)
        replay = json.loads((self.out/"report.json").read_text())
        self.assertFalse(replay["network_used"])
        self.assertEqual(replay["rpc_requests"], [])
        self.assertEqual(report["reconciliation"], replay["reconciliation"])
        self.assertEqual(report["evidence_sha256"], replay["evidence_sha256"])
        self.assertEqual(before, [p.read_bytes() for p in (self.report, self.evidence)])

    def test_unavailable_capture_is_retained_replayable_and_never_passes(self):
        self.client = o.Client(Opener(self.selected, lambda p,v: None if p["method"] == "getBlock" else v), pause=lambda _: None)
        self.assertEqual(self.call(), 0)
        report = json.loads((self.out/"report.json").read_text())
        self.assertEqual(report["status"], "block-ordering-unavailable")
        self.assertTrue(report["local_replay_verified"])
        self.assertEqual(len(report["rpc_requests"]), 2)

    def test_input_tampering_and_missing_mode_stop_before_traffic(self):
        self.assertEqual(self.call(()), 1)
        self.assertFalse(self.out.exists())
        self.evidence.write_bytes(self.evidence.read_bytes()+b"x")
        self.assertEqual(self.call(), 1)
        self.assertEqual(self.client.calls, [])
        self.assertFalse(self.out.exists())

    def test_existing_output_and_argument_secrets_are_preserved_or_sanitized(self):
        self.out.mkdir(); (self.out/"keep").write_text("preserve")
        self.assertEqual(self.call(), 1)
        self.assertEqual((self.out/"keep").read_text(), "preserve")
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.call(("--read-public-rpc", "--api-key", "SENSITIVE-KEY")), 1)
        self.assertNotIn("SENSITIVE-KEY", self.messages.getvalue())
