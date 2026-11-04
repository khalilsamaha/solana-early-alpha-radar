"""Transport context must follow the active signed preparation, never its ancestor."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import exit_submission as m
from unsigned_exit_replacement_checks import case


def floor(record):
    e=record['evidence']
    return max(e['simulationItem']['result']['context']['slot'],
        e['capture']['evidence']['accounts']['result']['context']['slot'],e['price']['quote']['contextSlot'])

class ContextTests(unittest.TestCase):
    def signing(self,c,b,sha):
        # Isolate this consumer; the actual independent signer and handoff replay
        # are exercised by the connected replacement regression.
        def replay(book,now,*,_preparation_sink):
            _preparation_sink(m.handoff.preparation.saved(book,now))
            return {'signed':{},'request':{'preparationSha256':sha,'feeCapLamports':'10000'}}
        with patch.object(m.handoff,'read',side_effect=replay):
            return m.ExitSubmission(b).signing()

    def test_later_replacement_fences_blockhash_fee_and_saved_boundary_proof(self):
        with case() as c:
            b=c.book()
            try:old_floor=floor(m.handoff.preparation.original_saved(b,c.clock()))
            finally:b.close()
            r=c.run();b=c.book()
            try:
                active=m.handoff.preparation.saved(b,c.clock());new_floor=floor(active)
                self.assertGreater(new_floor,old_floor)
                state=self.signing(c,b,r['recordSha256'])
                self.assertEqual(state['minimumContextSlot'],new_floor)
                received=lambda value:dict(state='received',result=value)
                proof=dict(genesisBefore=received(m.transport.GENESIS['devnet']),
                    genesisAfter=received(m.transport.GENESIS['devnet']),
                    blockhash=received(dict(context={'slot':new_floor},value=True)),
                    fee=received(dict(context={'slot':new_floor},value=5000)))
                self.assertEqual(m.proof_check(proof,state),new_floor)
                for field in ('blockhash','fee'):
                    stale=deepcopy(proof);stale[field]['result']['context']['slot']=old_floor
                    with self.subTest(field=field),self.assertRaises(ValueError):m.proof_check(stale,state)
            finally:b.close()

    def test_original_only_uses_its_own_evidence_and_rejects_wrong_signing_hash(self):
        with case() as c:
            b=c.book()
            try:
                state=self.signing(c,b,c.expected)
                self.assertEqual(state['minimumContextSlot'],floor(m.handoff.preparation.original_saved(b,c.clock())))
                with self.assertRaisesRegex(ValueError,'exit-preparation-required'):
                    self.signing(c,b,'0'*64)
            finally:b.close()

    def test_corrupt_replacement_cannot_fall_back_to_original_context(self):
        with case() as c:
            r=c.run();b=c.book()
            try:
                b.db.execute("UPDATE admission_exit_replacement SET hash=?",('0'*64,))
                with self.assertRaises(ValueError):self.signing(c,b,r['recordSha256'])
            finally:b.close()

    def test_actual_handoff_publishes_only_successfully_replayed_active_evidence(self):
        from exit_submission_checks import signed_case
        with signed_case() as c:
            b=c.book()
            try:
                records=[];saved=m.handoff.preparation.saved
                with patch.object(m.handoff.preparation,'saved',wraps=saved) as replay:
                    state=m.ExitSubmission(b).signing()
                    self.assertEqual(replay.call_count,1)
                m.handoff.read(b,c.now,_preparation_sink=records.append)
                self.assertEqual(len(records),1)
                self.assertEqual(m.digest(records[0]),state['request']['preparationSha256'])
                b.db.execute("UPDATE admission_exit_signing SET hash=? WHERE seq=2",('0'*64,))
                unpublished=[]
                with self.assertRaises(ValueError):m.handoff.read(b,c.now,_preparation_sink=unpublished.append)
                self.assertEqual(unpublished,[])
            finally:b.close()

if __name__=='__main__':unittest.main()
