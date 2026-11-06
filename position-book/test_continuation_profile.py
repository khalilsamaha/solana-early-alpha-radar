from types import SimpleNamespace
import unittest
import continuation_profile_cli as p


class ProfileTests(unittest.TestCase):
    def test_categories_omit_arbitrary_code_names_paths_and_payloads(self):
        rows=[SimpleNamespace(code=SimpleNamespace(co_filename='/private/key/canonical_replay.py'),
                             callcount=3,inlinetime=.01,totaltime=.03),
              SimpleNamespace(code='arbitrary private payload',callcount=1,inlinetime=.02,totaltime=.02)]
        out=p.summarize(SimpleNamespace(getstats=lambda:rows))
        self.assertEqual(out['canonical-comparison']['selfMs'],10)
        self.assertNotIn('private',str(out));self.assertEqual(len(out),2)

    def test_wrapper_preserves_result_and_records_failure(self):
        profiles=[]
        self.assertEqual(p.instrument(lambda x:x+1,profiles)(4),5)
        def fail():raise ValueError('failure')
        with self.assertRaisesRegex(ValueError,'failure'):p.instrument(fail,profiles)()
        self.assertEqual(len(profiles),2)
        self.assertTrue(all(g['selfMs']>=0 for x in profiles for g in x.values()))

    def test_disabled_scope_does_not_profile_fixture_calls(self):
        profiles=[]
        self.assertEqual(p.instrument(lambda:3,profiles,enabled=lambda:False)(),3)
        self.assertEqual(profiles,[])

    def test_unknown_phase_rejected_before_importing_rehearsal(self):
        with self.assertRaises(ValueError):p.run('live')

if __name__=='__main__':unittest.main()
