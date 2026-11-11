import contextlib
import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import signal
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import rpc_probe as r

MINT = "1" * 31 + "2"
SIG = "1" * 63 + "2"
PAYER = "1" * 31 + "9"
CANDIDATE = {"mint": MINT, "signature": SIG, "received_at_ms": 1_800_000_000_000 - 180_000}
STATUS = {"slot": 100, "confirmationStatus": "finalized", "err": None}


def tx(candidate=CANDIDATE, program=r.TOKEN):
    return {"slot": 100, "version": 0, "meta": {"err": None, "innerInstructions": []},
            "transaction": {"signatures": [candidate["signature"]], "message": {
                "accountKeys": [{"pubkey": PAYER, "signer": True},
                                {"pubkey": candidate["mint"], "signer": False},
                                {"pubkey": program, "signer": False}],
                "instructions": [{"programId": program, "parsed": {"type": "initializeMint2",
                    "info": {"mint": candidate["mint"], "decimals": 6, "mintAuthority": PAYER}}}]}}}


def account(program=r.TOKEN):
    return {"context": {"slot": 200}, "value": {"owner": program, "executable": False,
        "data": {"parsed": {"type": "mint", "info": {"decimals": 6, "isInitialized": True}}}}}


class Opener:
    def __init__(self, picked=None):
        self.picked = picked or [CANDIDATE]
        self.requests = []
        self.override = None

    def open(self, request, timeout):
        payload = json.loads(request.data)
        self.requests.append((request, timeout))
        method, params = payload["method"], payload["params"]
        if self.override:
            return self.override(payload)
        if method == "getGenesisHash":
            value = r.GENESIS
        elif method == "getSignatureStatuses":
            value = {"context": {"slot": 200}, "value": [STATUS for _ in self.picked]}
        elif method == "getTransaction":
            value = tx(next(c for c in self.picked if c["signature"] == params[0]))
        else:
            value = account()
        return io.BytesIO(json.dumps({"jsonrpc": "2.0", "id": payload["id"], "result": value}).encode())


class RpcTests(unittest.TestCase):
    def client(self, opener=None):
        return r.Client(opener or Opener(), pause=lambda _: None)

    def test_finalized_identity_initialization_and_account_reconcile(self):
        client = self.client()
        result = r.reconcile([CANDIDATE], client)
        self.assertEqual(result["status"], "rpc-facts-reconciled-live-blocked")
        self.assertEqual(result["cases"][0]["decimals"], 6)
        self.assertEqual(result["cases"][0]["slot"], 100)
        self.assertTrue(result["genesis_verified_before_and_after"])
        self.assertFalse(result["creator_verified"])
        self.assertFalse(result["curve_state_verified"])
        self.assertNotIn(MINT, json.dumps(result))
        self.assertEqual(len(client.calls), 5)

    def test_three_cases_use_exactly_nine_requests_without_writes(self):
        picked = [{"mint": "1" * 31 + c, "signature": "1" * 63 + c} for c in "234"]
        client = self.client(Opener(picked))
        self.assertEqual(r.reconcile(picked, client)["status"], "rpc-facts-reconciled-live-blocked")
        self.assertEqual(len(client.calls), 9)
        self.assertEqual(client.request("getGenesisHash", [])["state"], "request-budget-exhausted")
        with self.assertRaises(r.CaptureError):
            client.request("sendTransaction", [])

    def test_fixed_endpoint_finalized_requests_and_no_auth(self):
        opener = Opener()
        r.reconcile([CANDIDATE], self.client(opener))
        for request, timeout in opener.requests:
            self.assertEqual(request.full_url, r.ENDPOINT)
            self.assertEqual(request.get_method(), "POST")
            self.assertNotIn("Authorization", request.headers)
            self.assertLessEqual(timeout, 5)
            p = json.loads(request.data)
            if p["method"] in {"getTransaction", "getAccountInfo"}:
                self.assertEqual(p["params"][1]["commitment"], "finalized")

    def test_signature_slot_success_and_version_mismatch_rejected(self):
        variants = []
        a = tx(); a["transaction"]["signatures"][0] = "1" * 63 + "3"; variants.append(a)
        a = tx(); a["slot"] = 101; variants.append(a)
        a = tx(); a["meta"]["err"] = {}; variants.append(a)
        a = tx(); a["version"] = 1; variants.append(a)
        a = tx(); a["slot"] = True; variants.append(a)
        for value in variants:
            with self.assertRaises(ValueError):
                r.transaction_facts(CANDIDATE, STATUS, 200, value)

    def test_unfinalized_failed_and_missing_history_remain_unknown(self):
        self.assertEqual(r.transaction_facts(CANDIDATE, None, 200, None)["state"], "signature-not-found-unknown")
        self.assertEqual(r.transaction_facts(CANDIDATE, {**STATUS, "confirmationStatus": "confirmed"}, 200, tx())["state"], "not-finalized")
        self.assertEqual(r.transaction_facts(CANDIDATE, {**STATUS, "err": {}}, 200, tx())["state"], "transaction-failed")
        self.assertEqual(r.transaction_facts(CANDIDATE, STATUS, 200, None)["state"], "transaction-history-unavailable")

    def test_inner_token2022_initialization_is_supported(self):
        value = tx(program=r.TOKEN_2022)
        init = value["transaction"]["message"]["instructions"][0]
        value["transaction"]["message"]["instructions"] = [{"programId": "1" * 32, "accounts": []}]
        value["meta"]["innerInstructions"] = [{"index": 0, "instructions": [init]}]
        facts = r.transaction_facts(CANDIDATE, STATUS, 200, value)
        self.assertEqual(facts["token_program"], r.TOKEN_2022)
        self.assertTrue(r.account_matches(facts, account(r.TOKEN_2022)))

    def test_missing_duplicate_and_wrong_program_initialization_not_verified(self):
        for variant in ("missing", "duplicate", "wrong-program"):
            value = tx(); instructions = value["transaction"]["message"]["instructions"]
            if variant == "missing": instructions.clear()
            if variant == "duplicate": instructions.append(copy.deepcopy(instructions[0]))
            if variant == "wrong-program": instructions[0]["programId"] = "1" * 32
            self.assertEqual(r.transaction_facts(CANDIDATE, STATUS, 200, value)["state"], "initialization-not-uniquely-observed")

    def test_decimals_are_never_hardcoded_or_inferred_from_trader(self):
        value = tx(); value["transaction"]["message"]["instructions"][0]["parsed"]["info"]["decimals"] = 9
        facts = r.transaction_facts(CANDIDATE, STATUS, 200, value)
        self.assertEqual(facts["decimals"], 9)
        self.assertFalse(r.account_matches(facts, account()))
        value["transaction"]["message"]["instructions"][0]["parsed"]["info"]["decimals"] = True
        with self.assertRaises(ValueError):
            r.transaction_facts(CANDIDATE, STATUS, 200, value)

    def test_mint_membership_and_inner_index_checked(self):
        value = tx(); value["transaction"]["message"]["accountKeys"][1]["pubkey"] = "1" * 31 + "3"
        with self.assertRaises(ValueError): r.transaction_facts(CANDIDATE, STATUS, 200, value)
        value = tx(); value["meta"]["innerInstructions"] = [{"index": 5, "instructions": []}]
        with self.assertRaises(ValueError): r.transaction_facts(CANDIDATE, STATUS, 200, value)

    def test_account_owner_context_decimals_and_initialization_checked(self):
        facts = r.transaction_facts(CANDIDATE, STATUS, 200, tx())
        variants = [None, {"context": None}]
        a = account(); a["value"]["owner"] = r.TOKEN_2022; variants.append(a)
        a = account(); a["context"]["slot"] = 99; variants.append(a)
        a = account(); a["value"]["data"]["parsed"]["info"]["isInitialized"] = False; variants.append(a)
        a = account(); a["value"]["executable"] = True; variants.append(a)
        for value in variants:
            self.assertFalse(r.account_matches(facts, value))

    def test_genesis_mismatch_stops_before_transaction_requests(self):
        opener = Opener()
        opener.override = lambda p: io.BytesIO(json.dumps({"jsonrpc": "2.0", "id": p["id"], "result": "WRONG"}).encode())
        client = self.client(opener)
        self.assertEqual(r.reconcile([CANDIDATE], client)["status"], "rpc-feasibility-incomplete")
        self.assertEqual(len(client.calls), 1)

    def test_invalid_status_context_stops_without_transaction_fetch(self):
        for context in (None, {}, {"slot": True}, {"slot": "200"}):
            opener = Opener()
            def response(p):
                value = r.GENESIS if p["method"] == "getGenesisHash" else {"context": context, "value": [STATUS]}
                return io.BytesIO(json.dumps({"jsonrpc": "2.0", "id": p["id"], "result": value}).encode())
            opener.override = response
            client = self.client(opener)
            result = r.reconcile([CANDIDATE], client)
            self.assertEqual(result["status"], "rpc-feasibility-incomplete")
            self.assertEqual(len(client.calls), 2)
            self.assertEqual(r.replay_bundle({"schema_version": 1, "candidates": [CANDIDATE], "rpc_evidence": client.evidence}), result)

    def test_final_genesis_failure_downgrades_pass_and_replays(self):
        opener = Opener()
        original = opener.open
        def fail_last(request, timeout):
            if json.loads(request.data)["id"] == 5:
                raise HTTPError(r.ENDPOINT, 429, "PRIVATE", {}, io.BytesIO(b"PRIVATE"))
            return original(request, timeout)
        with patch.object(opener, "open", side_effect=fail_last):
            client = self.client(opener)
            result = r.reconcile([CANDIDATE], client)
        self.assertEqual(result["status"], "rpc-feasibility-incomplete")
        self.assertEqual(result["cases"][0]["state"], "genesis-recheck-unavailable")
        self.assertEqual(len(client.calls), 5)
        self.assertEqual(r.replay_bundle({"schema_version": 1, "candidates": [CANDIDATE], "rpc_evidence": client.evidence}), result)

    def test_http_429_stops_no_retry_and_no_error_text_exported(self):
        opener = Opener()
        def fail(p):
            raise HTTPError(r.ENDPOINT, 429, "PRIVATE-ERROR", {}, io.BytesIO(b"PRIVATE-BODY"))
        opener.override = fail
        client = self.client(opener)
        result = r.reconcile([CANDIDATE], client)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["http_status"], 429)
        self.assertNotIn("PRIVATE", json.dumps([result, client.evidence, client.calls]))

    def test_invalid_envelopes_and_response_caps_stop(self):
        for raw in (b'{"jsonrpc":"2.0","id":99,"result":1}', b'{"id":1,"id":1}', b"x" * (r.MAX_RESPONSE + 1)):
            opener = Opener(); opener.override = lambda p, raw=raw: io.BytesIO(raw)
            client = self.client(opener)
            self.assertEqual(client.request("getGenesisHash", [])["state"], "rpc-unavailable")
            self.assertEqual(client.request("getGenesisHash", [])["state"], "request-budget-exhausted")

    def test_redirect_handler_does_not_follow(self):
        self.assertIsNone(r.NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.invalid"))

    def test_total_request_deadline_preserved(self):
        now = [100.0]
        client = r.Client(Opener(), clock=lambda: now[0], pause=lambda _: None)
        now[0] += 30
        self.assertEqual(client.request("getGenesisHash", [])["state"], "request-budget-exhausted")
        self.assertEqual(client.calls, [])

    def test_alarm_restored_and_existing_timer_not_overridden(self):
        previous = signal.getsignal(signal.SIGALRM)
        with r.alarm(1):
            pass
        self.assertEqual(signal.getsignal(signal.SIGALRM), previous)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        signal.setitimer(signal.ITIMER_REAL, 10)
        try:
            with self.assertRaises(r.CaptureError):
                with r.alarm(1): pass
            self.assertGreater(signal.getitimer(signal.ITIMER_REAL)[0], 8)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)

    def test_alarm_interrupts_stalled_operation_and_restores_handler(self):
        previous = signal.getsignal(signal.SIGALRM)
        with self.assertRaises(TimeoutError):
            with r.alarm(0.01):
                time.sleep(1)
        self.assertEqual(signal.getsignal(signal.SIGALRM), previous)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_private_evidence_replays_without_network(self):
        client = self.client(); result = r.reconcile([CANDIDATE], client)
        bundle = {"schema_version": 1, "candidates": [CANDIDATE], "rpc_evidence": client.evidence}
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            self.assertEqual(r.replay_bundle(bundle), result)
        bundle["rpc_evidence"][0]["method"] = "getAccountInfo"
        with self.assertRaises(r.CaptureError): r.replay_bundle(bundle)

    def test_invalid_and_duplicate_candidate_identifiers_refused(self):
        self.assertFalse(r.identifier("2" * 32, 32))
        with self.assertRaises(r.CaptureError): r.reconcile([CANDIDATE, CANDIDATE], self.client())
        with self.assertRaises(r.CaptureError): r.reconcile([{**CANDIDATE, "signature": "bad"}], self.client())


class RpcHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "radar.sqlite"
    def tearDown(self):
        self.temp.cleanup()
    def fixture(self):
        db = sqlite3.connect(self.path)
        try:
            db.execute("CREATE TABLE launch_registry(mint TEXT PRIMARY KEY,received_at INTEGER,data TEXT)")
            db.execute("CREATE INDEX launch_registry_received ON launch_registry(received_at)")
            for c in "2345":
                mint, sig, at = "1" * 31 + c, "1" * 63 + c, CANDIDATE["received_at_ms"] - int(c)
                row = {"version": "launch-registry-1", "source": "pumpportal:create", "mint": mint,
                       "receivedAt": at, "availableAt": at, "fields": {"signature": sig}}
                db.execute("INSERT INTO launch_registry VALUES(?,?,?)", (mint, at, json.dumps(row)))
            db.commit()
        finally:
            db.close()
    def test_selection_uses_three_mature_valid_records_without_writing(self):
        self.fixture(); before = self.path.read_bytes()
        picked, selection = r.candidates(self.path, now_ms=1_800_000_000_000)
        self.assertEqual(len(picked), 3)
        self.assertEqual(selection["records_inspected"], 3)
        self.assertEqual(before, self.path.read_bytes())
    def test_missing_source_is_never_created(self):
        with self.assertRaises(FileNotFoundError): r.candidates(self.path)
        self.assertFalse(self.path.exists())
    def test_recent_or_old_records_not_used(self):
        self.fixture()
        self.assertEqual(r.candidates(self.path, now_ms=CANDIDATE["received_at_ms"] + 100)[0], [])
        self.assertEqual(r.candidates(self.path, now_ms=1_800_000_000_000 + 2 * 86_400_000)[0], [])
    def test_invalid_and_oversized_source_records_are_not_requested(self):
        self.fixture()
        db = sqlite3.connect(self.path)
        try:
            db.execute("UPDATE launch_registry SET data=? WHERE mint=?", ("x" * 5000, "1" * 31 + "2"))
            db.execute("UPDATE launch_registry SET data=? WHERE mint=?", ('{"fields":{"signature":"bad"}}', "1" * 31 + "3"))
            db.commit()
        finally:
            db.close()
        picked, selection = r.candidates(self.path, now_ms=1_800_000_000_000)
        self.assertEqual(len(picked), 2)
        self.assertEqual(selection["rejected_or_duplicate"], 2)
    def test_missing_index_refuses_fallback_scan(self):
        self.fixture()
        db = sqlite3.connect(self.path)
        try:
            db.execute("DROP INDEX launch_registry_received")
            db.commit()
        finally:
            db.close()
        with self.assertRaises(r.CaptureError):
            r.candidates(self.path, now_ms=1_800_000_000_000)
    def test_cli_requires_explicit_read_flag(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(r.main(["--project", str(self.root), "--output-directory", str(self.root / "out")]), 1)
        self.assertFalse((self.root / "out").exists())
    def test_live_cli_with_mock_rpc_preserves_private_replay_and_summary(self):
        client = r.Client(Opener(), pause=lambda _: None)
        out = self.root / "out"
        with patch.object(r, "discover_database", return_value=self.path), patch.object(r, "candidates", return_value=([CANDIDATE], {"selected": 1})), patch.object(r, "Client", return_value=client):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(r.main(["--project", str(self.root), "--output-directory", str(out), "--read-public-rpc"]), 0)
        report = json.loads((out / "report.json").read_text())
        bundle = json.loads(gzip.decompress((out / "evidence.json.gz").read_bytes()))
        self.assertEqual(report["status"], "rpc-facts-reconciled-live-blocked")
        self.assertTrue(report["local_replay_verified"])
        self.assertEqual(r.replay_bundle(bundle), report["reconciliation"])
        self.assertNotIn(SIG, (out / "report.json").read_text())
        self.assertNotIn(MINT, (out / "report.json").read_text())
        self.assertEqual((out / "evidence.json.gz").stat().st_mode & 0o777, 0o600)
        self.assertEqual(hashlib.sha256((out / "evidence.json.gz").read_bytes()).hexdigest(), report["evidence_sha256"])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(r.main(["--project", str(self.root), "--output-directory", str(out), "--read-public-rpc"]), 1)

    def test_unexpected_failure_keeps_actual_request_accounting(self):
        client = r.Client(Opener(), pause=lambda _: None)
        def partial(*_):
            client.request("getGenesisHash", [])
            raise RuntimeError("PRIVATE")
        out = self.root / "out"
        with patch.object(r, "discover_database", return_value=self.path), patch.object(r, "candidates", return_value=([CANDIDATE], {"selected": 1})), patch.object(r, "Client", return_value=client), patch.object(r, "reconcile", side_effect=partial):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(r.main(["--project", str(self.root), "--output-directory", str(out), "--read-public-rpc"]), 0)
        report = json.loads((out / "report.json").read_text())
        bundle = json.loads(gzip.decompress((out / "evidence.json.gz").read_bytes()))
        self.assertEqual(report["status"], "probe-unavailable")
        self.assertFalse(report["local_replay_verified"])
        self.assertEqual(len(report["rpc_requests"]), 1)
        self.assertEqual(len(bundle["rpc_evidence"]), 1)
        self.assertNotIn("PRIVATE", (out / "report.json").read_text())
