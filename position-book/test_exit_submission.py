import gzip
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from unittest.mock import patch

import exit_submission as m
from exit_submission_checks import signed_case,FakeRpc,submit,recover,status
from contract import digest

HERE=Path(__file__).resolve().parent

class ExitTests(unittest.TestCase):
    def test_portable_cli(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'r.gz';cmd=[sys.executable,'-E','-s',str(HERE/'exit_submission_cli.py'),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            raw=out.read_bytes();v=json.loads(gzip.decompress(raw));self.assertEqual(v['casesPassed'],24)
            self.assertTrue(all(x=='passed' for x in v['cases'].values()));self.assertFalse(v['receiptEffectsReconciled'])
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(raw,out.read_bytes())
            self.assertNotEqual(subprocess.run(cmd+['--allow-devnet-submit'],capture_output=True).returncode,0)

    def test_default_optin_required_before_access(self):
        with patch.object(m.view.cycles.c,'source_lock',side_effect=AssertionError('access')):
            with self.assertRaisesRegex(ValueError,'explicit-devnet-submit-required'):m.submit('/missing','x','y')

    def test_source_mutation_during_preflight_refuses_send(self):
        with signed_case() as c:
            original=m.view.read_locked;calls=[]
            def changed(*args):
                v=deepcopy(original(*args));v['ledgerHeadSha256']='0'*64;return v
            def after(method):
                if method=='getFeeForMessage':calls.append(True)
            def reader(*args):return changed(*args) if calls else original(*args)
            rpc=FakeRpc(c,callback=after)
            with patch.object(m.view,'read_locked',reader):
                with self.assertRaisesRegex(ValueError,'exit-signing-source-changed'):submit(c,rpc)
            self.assertFalse(status(c)['applicationSendBoundaryRecorded'])
            self.assertFalse(any(q['method']=='sendTransaction' for q in rpc.requests))

    def test_commit_crash_and_expiry_never_retry(self):
        for fault in ('exception','expiry'):
            with self.subTest(fault=fault),signed_case() as c:
                mark=m.ExitSubmission.mark;rpc=FakeRpc(c)
                def after(*args):
                    v=mark(*args)
                    if fault=='exception':raise OSError('after commit')
                    c.now+=30000;return v
                with patch.object(m.ExitSubmission,'mark',after):
                    with self.assertRaises((OSError,ValueError)):submit(c,rpc)
                self.assertFalse(any(q['method']=='sendTransaction' for q in rpc.requests))
                self.assertEqual(status(c)['state'],'exit-submission-unknown')
                self.assertEqual(submit(c)['networkRequestsThisRun'],0)

    def test_empty_boundary_table_fails_closed(self):
        with signed_case() as c:
            # A storage-level trigger failure aborts the single transaction.
            b=c.book()
            try:
                b.db.executescript('CREATE TABLE admission_exit_submission (id INTEGER PRIMARY KEY,value TEXT);')
            finally:b.close()
            rpc=FakeRpc(c)
            with self.assertRaisesRegex(ValueError,'exit-transport-record'):submit(c,rpc)
            self.assertFalse(rpc.requests)

    def test_precommit_storage_failure_rolls_back(self):
        with signed_case() as c:
            original=m.encoded;rpc=FakeRpc(c)
            def fail(v):
                if isinstance(v,dict) and v.get('format')==m.VERSION:raise OSError('synthetic storage failure')
                return original(v)
            with patch.object(m,'encoded',fail):
                with self.assertRaises(OSError):submit(c,rpc)
            self.assertFalse(status(c)['applicationSendBoundaryRecorded'])
            self.assertFalse(any(q['method']=='sendTransaction' for q in rpc.requests))

    def test_blockhash_context_cannot_precede_collected_evidence(self):
        import io
        with signed_case() as c:
            rpc=FakeRpc(c);original=rpc.open
            def stale(request,timeout=None):
                r=json.load(original(request,timeout))
                if json.loads(request.data)['method']=='isBlockhashValid':r['result']['context']['slot']=100
                return io.BytesIO(json.dumps(r).encode())
            with patch.object(rpc,'open',stale):
                with self.assertRaisesRegex(ValueError,'rpc-slot-invalid'):submit(c,rpc)
            self.assertFalse(status(c)['applicationSendBoundaryRecorded'])

    def test_writer_and_wallet_locks(self):
        with signed_case() as c:
            original=m.handoff.current;observed=[]
            def check(*args):
                # Second invocation is under the durable mark transaction.
                observed.append(True)
                if len(observed)==2:
                    db=sqlite3.connect(c.path,timeout=0)
                    try:
                        with self.assertRaises(sqlite3.OperationalError):db.execute('BEGIN IMMEDIATE')
                    finally:db.close()
                return original(*args)
            with patch.object(m.handoff,'current',check):submit(c)
            self.assertEqual(len(observed),2)

    def test_capture_cap_and_saved_replay(self):
        with signed_case() as c:
            submit(c)
            for _ in range(m.MAX_CAPTURES):recover(c,FakeRpc(c,missing=True))
            rpc=FakeRpc(c)
            with self.assertRaisesRegex(ValueError,'exit-capture-cap'):recover(c,rpc)
            self.assertFalse(rpc.requests)
        with signed_case() as c:
            submit(c);original=m.ExitSubmission.save_capture
            def after(*args):original(*args);raise OSError('after save')
            with patch.object(m.ExitSubmission,'save_capture',after):
                with self.assertRaises(OSError):recover(c)
            rpc=FakeRpc(c);self.assertEqual(recover(c,rpc)['state'],'exit-finalized-evidence');self.assertFalse(rpc.requests)

    def test_tampered_boundary_and_capture(self):
        with signed_case() as c:
            submit(c);b=c.book()
            try:
                v=json.loads(b.db.execute('SELECT value FROM admission_exit_submission').fetchone()[0]);v['signature']=c.wallet
                b.db.execute('UPDATE admission_exit_submission SET value=?',(m.encoded(v),))
            finally:b.close()
            with self.assertRaisesRegex(ValueError,'exit-boundary-binding'):status(c)
        with signed_case() as c:
            submit(c);recover(c);b=c.book()
            try:b.db.execute("UPDATE admission_exit_rpc_captures SET hash=?",('0'*64,))
            finally:b.close()
            with self.assertRaisesRegex(ValueError,'exit-capture-binding'):status(c)

    def test_inconsistent_terminal_claims_quarantine(self):
        with signed_case() as c:
            submit(c);recover(c)
            b=c.book()
            try:
                s=m.ExitSubmission(b);ev=deepcopy(s.captures()[0]['rpcEvidence'])
                # Header evidence does not assert balance reconciliation, and
                # conflicting same-signature terminal evidence remains visible.
                ev['transaction']['result']['meta']['err']={'InstructionError':[2,'Custom']}
                ev['signatureStatus']['result']['value'][0]['err']=ev['transaction']['result']['meta']['err']
                s.save_capture(c.now,ev);self.assertEqual(s.status()['state'],'quarantined')
            finally:b.close()

    def test_malformed_finality_headers_cannot_be_accepted(self):
        with signed_case() as c:
            submit(c);recover(c);b=c.book()
            try:
                s=m.ExitSubmission(b);capture=s.captures()[0];state=s.signing()
                mutations=[lambda v:v['rpcEvidence']['signatureStatus']['result']['value'][0].pop('confirmations'),
                    lambda v:v['rpcEvidence']['signatureStatus']['result']['value'][0].update(slot=True),
                    lambda v:v['rpcEvidence']['transaction']['result'].update(slot=99),
                    lambda v:v['rpcEvidence']['transaction']['result']['meta'].update(err='contradictory'),
                    lambda v:v['rpcEvidence']['signatureStatus']['result']['context'].update(slot=99)]
                for fn in mutations:
                    v=deepcopy(capture);fn(v);kind,_=m.classify(v,state,100);self.assertNotIn(kind,m.TERMINAL)
            finally:b.close()

if __name__=='__main__':unittest.main()
