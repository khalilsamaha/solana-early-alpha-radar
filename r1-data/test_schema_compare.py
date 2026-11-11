import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import schema_compare as s
from test_event_inspect import accepted, defaults, encode, fixture, key


def candidate_tx(*, fee=0, tail=b"", changes=None):
    tx = fixture()
    values = defaults("TradeEvent")
    parent = tx["transaction"]["message"]["instructions"][1]
    values.update(mint=parent["accounts"][1], user=parent["accounts"][13], is_buy=True,
                  token_amount=123, sol_amount=456, quote_amount=456,
                  quote_mint=s.base.SYSTEM, ix_name="buy")
    values.update(changes or {})
    # Independent old-schema fixture encoder plus the documented u64 extension.
    raw = encode("TradeEvent", values) + fee.to_bytes(8, "little") + tail
    tx["meta"]["innerInstructions"][1]["instructions"][-1]["data"] = s.base.b58encode(s.base.EVENT_TAG + raw)
    return tx


class ComparisonTests(unittest.TestCase):
    def compare(self, tx):
        report, bundle, _ = accepted(tx)
        return s.compare(report, bundle)

    def test_exact_match_preserves_default_mismatch_and_literal_name(self):
        result = self.compare(candidate_tx())
        case = result["cases"][0]
        self.assertEqual(case["baseline_state"], "creation-decoded-trade-schema-mismatch")
        event = case["trade_events"][0]
        self.assertEqual(event["candidate_state"], "exact-layout-and-transfer-match-diagnostic-only")
        self.assertEqual(event["bytes_consumed"], event["payload_bytes"])
        self.assertTrue(event["reencoded_bytes_match"])
        self.assertEqual(event["quote_transfer_fee_reported"], 0)
        self.assertEqual(event["event_ix_name_reported"], "buy")
        self.assertEqual(event["parent_instruction"], "buy_v2")
        for flag in ("fee_model_verified", "curve_reconstruction_accepted", "deployed_program_version_verified",
                     "archive_checksum_verified", "ix_name_mapping_verified", "paid_collection_enabled"):
            self.assertIs(result[flag], False)

    def test_nonzero_extension_and_shareholders_roundtrip_without_fee_acceptance(self):
        result = self.compare(candidate_tx(fee=2**64-1, changes={"shareholders": [{"address": key(999), "share_bps": 10000}],
                                                               "timestamp": -(2**63)}))
        event = result["cases"][0]["trade_events"][0]
        self.assertTrue(event["reencoded_bytes_match"])
        self.assertEqual(event["quote_transfer_fee_reported"], 2**64-1)
        self.assertFalse(result["fee_model_verified"])

    def test_every_extension_truncation_and_extra_tail_remain_unsupported(self):
        for extension_length in range(8):
            with self.subTest(extension_length=extension_length):
                tx = candidate_tx()
                event = tx["meta"]["innerInstructions"][1]["instructions"][-1]
                raw = s.base.b58decode(event["data"])
                event["data"] = s.base.b58encode(raw[:len(raw)-8+extension_length])
                result = self.compare(tx)["cases"][0]
                self.assertEqual(result["trade_events"][0]["candidate_state"], "unsupported")
        for tail in (b"\0", b"\0" * 8, b"unexpected"):
            event = self.compare(candidate_tx(tail=tail))["cases"][0]["trade_events"][0]
            self.assertEqual(event["candidate_state"], "unsupported")
            self.assertNotIn("quote_transfer_fee_reported", event)

    def test_identity_direction_and_transfer_disagreements_do_not_export_values(self):
        for changes in ({"mint": key(999)}, {"user": key(999)}, {"is_buy": False},
                        {"token_amount": 124}, {"sol_amount": 457}, {"quote_amount": 457},
                        {"quote_mint": s.base.WSOL}):
            with self.subTest(changes=changes):
                event = self.compare(candidate_tx(changes=changes))["cases"][0]["trade_events"][0]
                self.assertEqual(event["candidate_state"], "unsupported")
                self.assertNotIn("quote_transfer_fee_reported", event)

    def test_unsupported_provenance_cannot_be_rescued_by_new_layout(self):
        for field, value in (("programId", key(999)), ("stackHeight", 3), ("accounts", [key(999)])):
            tx = candidate_tx()
            tx["meta"]["innerInstructions"][1]["instructions"][-1][field] = value
            case = self.compare(tx)["cases"][0]
            self.assertEqual(case["state"], "baseline-unsupported")
            self.assertEqual(case["trade_events"], [])

    def test_no_trade_remains_transaction_scoped(self):
        case = self.compare(fixture(trade=False))["cases"][0]
        self.assertEqual(case["state"], "no-trade-in-this-transaction")
        self.assertEqual(case["trade_events"], [])

    def test_profile_and_replay_pins_are_required(self):
        with patch.object(s, "PROFILE_SHA256", "bad"):
            with self.assertRaises(s.CaptureError): self.compare(candidate_tx())
        original, bundle, _ = accepted(candidate_tx())
        for kind in ("source", "replay", "requests"):
            report = copy.deepcopy(original)
            if kind == "source": report["source_sha256"]["rpc_probe.py"] = "bad"
            elif kind == "replay": report["reconciliation"]["cases"][0]["decimals"] = 9
            else: report["rpc_requests"][0]["method"] = "getAccountInfo"
            with self.assertRaises(s.CaptureError): s.compare(report, bundle)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        report, _, compressed = accepted(candidate_tx())
        self.report = self.root / "report.json"; self.report.write_text(json.dumps(report))
        self.bundle = self.root / "evidence.json.gz"; self.bundle.write_bytes(compressed)
        self.output = self.root / "output.json"

    def tearDown(self): self.temp.cleanup()

    def call(self, extra=()):
        self.messages = io.StringIO()
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), contextlib.redirect_stdout(self.messages), contextlib.redirect_stderr(self.messages):
            return s.main(["--rpc-report", str(self.report), "--evidence", str(self.bundle), "--output", str(self.output), *extra])

    def test_offline_private_sanitized_and_input_preserving(self):
        before = [p.read_bytes() for p in (self.report, self.bundle)]
        self.assertEqual(self.call(), 0)
        result = json.loads(self.output.read_text())
        self.assertFalse(result["network_used"])
        self.assertFalse(result["credentials_loaded"])
        self.assertEqual(result["transactions_sent"], 0)
        self.assertEqual(result["evidence_sha256"], s.base.sha(before[1]))
        self.assertEqual(len(result["source_sha256"]), len(s.SOURCES))
        self.assertEqual(before, [p.read_bytes() for p in (self.report, self.bundle)])
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(key(113), self.output.read_text())

    def test_corruption_and_decompression_limit_create_no_report(self):
        with patch.object(s.base, "MAX_INPUT", 32): self.assertEqual(self.call(), 1)
        self.assertFalse(self.output.exists())
        self.bundle.write_bytes(self.bundle.read_bytes() + b"x")
        self.assertEqual(self.call(), 1)
        self.assertFalse(self.output.exists())

    def test_output_and_symlink_preservation(self):
        self.output.write_text("preserve")
        self.assertEqual(self.call(), 1)
        self.assertEqual(self.output.read_text(), "preserve")
        self.output.unlink(); self.output.symlink_to(self.report)
        self.assertEqual(self.call(), 1)
        self.assertTrue(self.output.is_symlink())

    def test_invalid_arguments_and_profile_failure_are_sanitized(self):
        self.assertEqual(self.call(("--api-key", "SENSITIVE-KEY")), 1)
        self.assertNotIn("SENSITIVE-KEY", self.messages.getvalue())
        with patch.object(s, "candidate_layout", side_effect=RuntimeError("SENSITIVE-KEY")):
            self.assertEqual(self.call(), 1)
        self.assertNotIn("SENSITIVE-KEY", self.messages.getvalue())
        self.assertFalse(self.output.exists())
