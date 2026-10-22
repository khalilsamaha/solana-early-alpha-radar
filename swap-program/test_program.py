import base64
import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from program import (audit, compare, deployment, PROGRAM, LOADER, GENESIS, MAX_ACCOUNT,
                     MAX_BASE64, boundaries)
from checks import fixture, edit, run, fake_key, decode, encoded, NOW
from program_capture import collect, ProgramClient
from program_cli import read_capture, MAX_REPORT


def rows(c):
    return c['evidence']['accounts']['result']['value']


def replies(c):
    return [copy.deepcopy(c['evidence'][n]['result']) for n in
            ('genesisBefore', 'bootstrap', 'accounts', 'blockTime', 'genesisAfter')]


class Opener:
    def __init__(self, values):
        self.values, self.calls = list(values), []

    def open(self, request, timeout):
        body = json.loads(request.data)
        self.calls.append((request, body, timeout))
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return io.BytesIO(json.dumps({'jsonrpc': '2.0', 'id': body['id'], 'result': value}).encode())


class ProgramTests(unittest.TestCase):
    def rejected(self, c, reason=None):
        r = audit(c)
        self.assertNotEqual(r['state'], 'deployment-observed', r)
        if reason:
            self.assertEqual(r['reason'], reason)
        for k, v in boundaries().items():
            self.assertEqual(r[k], v)
        return r

    def test_host_self_check(self):
        report = run()
        self.assertEqual(report['casesPassed'], 14)
        self.assertEqual(report['networkRequests'], 0)

    def test_upgradeable_and_no_authority_observations_never_authorize(self):
        for authority in (True, False):
            c = fixture(authority=authority)
            before = copy.deepcopy(c)
            r = audit(c)
            self.assertEqual(r['state'], 'deployment-observed')
            self.assertEqual(r['upgradeAuthority'] is not None, authority)
            self.assertEqual(r['deploymentSlot'], 90)
            for k, v in boundaries().items():
                self.assertEqual(r[k], v)
            self.assertEqual(before, c)

    def test_full_payload_padding_and_header_hashes_are_exact(self):
        c = fixture(); raw = base64.b64decode(rows(c)[1]['data'][0]); r = audit(c)
        self.assertEqual(r['payloadSha256'], hashlib.sha256(raw[45:]).hexdigest())
        self.assertEqual(r['metadataSha256'], hashlib.sha256(raw[:45]).hexdigest())
        self.assertEqual(r['accountDataSha256'], hashlib.sha256(raw).hexdigest())
        changed = audit(edit(copy.deepcopy(c), len(raw)-1, b'\x01'))
        self.assertNotEqual(r['payloadSha256'], changed['payloadSha256'])
        self.assertEqual(r['metadataSha256'], changed['metadataSha256'])

    def test_none_option_reserved_bytes_are_not_an_authority(self):
        c = edit(fixture(authority=False), 13, b'\xff'*32)
        self.assertIsNone(audit(c)['upgradeAuthority'])
        self.assertEqual(audit(c)['state'], 'deployment-observed')

    def test_program_and_network_fixed(self):
        for name, value in (('program', fake_key('other')), ('network', 'mainnet-beta'), ('format', 'bad')):
            c = fixture(); c[name] = value
            self.rejected(c, 'capture-format-or-program')

    def test_both_genesis_identities_checked(self):
        for name in ('genesisBefore', 'genesisAfter'):
            c = fixture(); c['evidence'][name]['result'] = GENESIS['mainnet-beta']
            self.rejected(c, 'wrong-cluster')

    def test_missing_evidence_never_partial_success(self):
        for name in fixture()['evidence']:
            c = fixture(); c['evidence'][name] = {'state': 'network-error'}
            self.rejected(c)

    def test_programdata_owner_executable_lamports_and_tag(self):
        for name, value in (('owner', PROGRAM), ('executable', True), ('lamports', 0), ('lamports', True)):
            c = fixture(); rows(c)[1][name] = value
            self.rejected(c)
        for tag in (0, 1, 2, 4):
            self.rejected(edit(fixture(), 0, tag.to_bytes(4, 'little')), 'programdata-tag')

    def test_program_executable_owner_pointer_layout(self):
        for target in ('bootstrap', 'accounts'):
            for name, value in (('owner', PROGRAM), ('executable', False)):
                c = fixture(); c['evidence'][target]['result']['value'][0][name] = value
                self.rejected(c)
        c = fixture(); rows(c)[0] = encoded(b'\x02\0\0\0'+decode(fake_key('new')), LOADER, executable=True)
        self.rejected(c, 'program-pointer-changed')

    def test_account_key_binding_and_null(self):
        c = fixture(); c['accountKeys'].reverse(); self.rejected(c, 'account-key-binding')
        for index in (0, 1):
            c = fixture(); rows(c)[index] = None; self.rejected(c)

    def test_strict_programdata_base64(self):
        for value in (['!','base64'], ['AA==\n','base64'], ['', 'base64+zstd'], {}, None):
            c = fixture(); rows(c)[1]['data'] = value; self.rejected(c)

    def test_size_cap_and_truncated_header(self):
        for length in (0, 44, 45, 108, MAX_ACCOUNT+1):
            c = fixture(); raw = bytearray(base64.b64decode(rows(c)[1]['data'][0]))
            raw = (raw + bytearray(max(0, length-len(raw))))[:length]
            rows(c)[1]['data'][0] = base64.b64encode(raw).decode(); self.rejected(c)

    def test_authority_tag_slot_and_elf_envelope(self):
        self.rejected(edit(fixture(), 12, b'\x02'), 'programdata-authority-option')
        self.rejected(edit(fixture(), 4, (102).to_bytes(8, 'little')), 'deployment-slot-after-snapshot')
        for offset, value in ((45, b'!'), (49, b'\x01'), (50, b'\x02'), (51, b'\x00')):
            self.rejected(edit(fixture(), offset, value), 'program-payload-envelope')

    def test_snapshot_order_time_binding_and_capture_budget(self):
        self.rejected(fixture(slot=99), 'snapshot-slot-regression')
        c = fixture(); c['blockTimeSlot'] = 102; self.rejected(c, 'block-time-slot-binding')
        for value in (None, True, -1, 0):
            c = fixture(); c['evidence']['blockTime']['result'] = value; self.rejected(c)
        for value in (True, NOW-1, NOW+45001):
            c = fixture(); c['finishedAtMs'] = value; self.rejected(c, 'capture-time-window')

    def test_comparison_detects_bytes_authority_redeployment_and_removal(self):
        for current, field in ((edit(fixture(slot=102), 120, b'\x01'), 'payloadSha256'),
                               (edit(fixture(slot=102), 13, decode(fake_key('new'))), 'upgradeAuthority'),
                               (edit(fixture(slot=102), 4, (100).to_bytes(8,'little')), 'deploymentSlot'),
                               (fixture(authority=False, slot=102), 'upgradeAuthority')):
            r = compare(current, fixture())
            self.assertEqual(r['state'], 'deployment-changed')
            self.assertIn(field, r['changedFields'])
            self.assertFalse(r['baselineTrusted'])

    def test_comparison_ignores_normal_lamport_and_observation_changes(self):
        c = fixture(slot=102); rows(c)[1]['lamports'] += 123
        r = compare(c, fixture())
        self.assertEqual(r['state'], 'deployment-unchanged')
        self.assertEqual(r['changedFields'], [])
        self.assertFalse(r['sameCapture'])

    def test_same_capture_is_explicit_not_independent_check(self):
        r = compare(fixture(), fixture())
        self.assertTrue(r['sameCapture']); self.assertFalse(r['independentConsensusVerified'])

    def test_comparison_rejects_regression_invalid_and_mixed_sources(self):
        r = compare(fixture(), fixture(slot=102))
        self.assertEqual(r['reason'], 'comparison-time-regression')
        c = fixture(); c['startedAtMs'] -= 1000; c['finishedAtMs'] -= 1000
        self.assertEqual(compare(c, fixture())['reason'], 'comparison-time-regression')
        c = fixture(); c['origin'] = 'public-rpc-capture'
        self.assertEqual(compare(c, fixture())['reason'], 'mixed-evidence-origins')
        self.assertEqual(compare({}, fixture())['state'], 'comparison-unavailable')
        self.assertEqual(compare(fixture(), None)['state'], 'not-compared')

    def test_collect_binds_program_pointer_batch_and_slot(self):
        opener = Opener(replies(fixture()))
        c = collect(opener=opener, now=lambda: NOW)
        self.assertEqual(audit(c)['state'], 'deployment-observed')
        self.assertEqual(len(opener.calls), 5)
        for request, body, timeout in opener.calls:
            self.assertEqual(request.full_url, 'https://api.devnet.solana.com')
            self.assertEqual(request.get_method(), 'POST')
            self.assertEqual(timeout, 10)
            self.assertNotIn('Authorization', request.headers)
            self.assertIn(body['method'], ProgramClient.METHODS)
        params = opener.calls[2][1]['params']
        self.assertEqual(params[0], fixture()['accountKeys'])
        self.assertEqual(params[1]['minContextSlot'], 100)
        self.assertNotIn('dataSlice', params[1])

    def test_collect_stops_each_network_failure_no_retries(self):
        for index in range(5):
            values = replies(fixture()); values[index] = urllib.error.URLError('private provider detail')
            opener = Opener(values); c = collect(opener=opener, now=lambda: NOW)
            self.assertEqual(len(opener.calls), index+1)
            self.rejected(c)
            self.assertNotIn('private provider detail', json.dumps(c))

    def test_rate_limit_preserved_without_retry(self):
        e = urllib.error.HTTPError('url', 429, 'arbitrary secret text', {}, None)
        opener = Opener([e]); c = collect(opener=opener, now=lambda: NOW)
        self.assertEqual(c['rpcRequestsAttempted'], 1)
        self.assertEqual(c['evidence']['genesisBefore']['httpStatus'], 429)
        self.assertNotIn('arbitrary secret text', json.dumps(c))

    def test_wrong_cluster_stops_before_account_reads(self):
        opener = Opener([GENESIS['mainnet-beta']]); c = collect(opener=opener, now=lambda: NOW)
        self.assertEqual(c['stoppedReason'], 'wrong-cluster')
        self.assertEqual(len(opener.calls), 1)

    def test_capture_deadline_stops_new_requests(self):
        ticks = iter([0, 0, 31])
        opener = Opener(replies(fixture()))
        c = collect(opener=opener, now=lambda: NOW, monotonic=lambda: next(ticks))
        self.assertEqual(c['stoppedReason'], 'capture-time-budget')
        self.assertEqual(len(opener.calls), 1)

    def test_transport_caps_and_projection(self):
        c = fixture(); rows(c)[1]['secret'] = 'do-not-export'
        opener = Opener(replies(c)); captured = collect(opener=opener, now=lambda: NOW)
        self.assertNotIn('do-not-export', json.dumps(captured))
        c = fixture(); rows(c)[1]['data'][0] = 'A'*(MAX_BASE64+1)
        captured = collect(opener=Opener(replies(c)), now=lambda: NOW)
        self.assertEqual(captured['evidence']['accounts']['state'], 'invalid-program-response')
        self.assertEqual(captured['rpcRequestsAttempted'], 3)

    def test_raw_response_cap_and_duplicate_keys(self):
        class Raw:
            def __init__(self, raw): self.raw = raw
            def open(self, *args, **kwargs): return io.BytesIO(self.raw)
        for raw, expected in ((b'x'*(4*1024*1024+1), 'response-too-large'),
                               (b'{"id":1,"id":1,"jsonrpc":"2.0","result":null}', 'invalid-response')):
            c = collect(opener=Raw(raw), now=lambda: NOW)
            self.assertEqual(c['evidence']['genesisBefore']['state'], expected)
            self.assertEqual(c['rpcRequestsAttempted'], 1)

    def test_method_and_request_caps_and_no_data_slicing(self):
        client = ProgramClient(Opener([GENESIS['devnet']]*6))
        for method in ('sendTransaction', 'simulateTransaction', 'requestAirdrop'):
            with self.assertRaises(ValueError): client.request(method, [])
        with self.assertRaises(ValueError):
            client.request('getMultipleAccounts', [[PROGRAM], {'dataSlice': {'offset':0,'length':45}}])
        for _ in range(5): client.request('getGenesisHash', [])
        with self.assertRaises(ValueError): client.request('getGenesisHash', [])

    def test_proxy_and_redirect_policy(self):
        import urllib.request
        client = ProgramClient()
        self.assertFalse(any(isinstance(h, urllib.request.ProxyHandler) and h.proxies for h in client.opener.handlers))
        handler = next(h for h in client.opener.handlers if isinstance(h, urllib.request.HTTPRedirectHandler))
        self.assertIsNone(handler.redirect_request(None, None, 302, 'redirect', {}, 'https://other.example'))

    def test_cli_replay_recomputes_untrusted_summaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root/'source.json'; output = root/'output.json.gz'
            source.write_text(json.dumps({'format':'swap-program-report-1', 'capture':fixture(),
                                          'review':{'signingApproved':True, 'payloadSha256':'forged'}}))
            subprocess.run([sys.executable, 'program_cli.py', '--input', str(source), '--baseline', str(source),
                            '--output', str(output)], check=True, capture_output=True)
            r = json.loads(gzip.decompress(output.read_bytes()))
            self.assertEqual(r['currentRunNetworkRequests'], 0)
            self.assertEqual(r['review'], audit(fixture()))
            self.assertEqual(r['capture']['finishedAtMs'], NOW+500)
            self.assertTrue(r['comparison']['sameCapture'])
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            again = subprocess.run([sys.executable, 'program_cli.py', '--output', str(output)], capture_output=True)
            self.assertNotEqual(again.returncode, 0)

    def test_cli_selfcheck_and_input_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); output = root/'check.json.gz'
            subprocess.run([sys.executable, 'program_cli.py', '--output', str(output)], check=True, capture_output=True)
            r = json.loads(gzip.decompress(output.read_bytes())); r.pop('capturedAt')
            self.assertEqual(r, run())
            oversized = root/'oversized.gz'; oversized.write_bytes(gzip.compress(b' '*(MAX_REPORT+1)))
            with self.assertRaises(ValueError): read_capture(oversized)
            bad = root/'bad.json'; bad.write_text('{"format":1,"format":2}')
            with self.assertRaises(ValueError): read_capture(bad)


if __name__ == '__main__':
    unittest.main()
