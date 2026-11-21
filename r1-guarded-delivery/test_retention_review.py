import io
import unittest
import retention_review as r


class DestinationReviewTests(unittest.TestCase):
    def setUp(self):
        self.facts = dict.fromkeys(r.ATTESTATIONS, True)
        self.facts.update(bucket=r.BUCKET, prefix=r.PREFIX, final_manifest_bytes=100,
                          available_storage_bytes=100, included_retrieval_bytes=200)

    def test_null_or_false_receipts_and_wrong_binding_hold(self):
        for key, value in (("bucket_private", False), ("independent_reader_can_restore_version_by_id", False),
                           ("zero_incremental_cost_for_operations_and_retention", None),
                           ("bucket", "another"), ("prefix", "r1-rehearsal/")):
            with self.subTest(key=key):
                self.assertEqual(r.assess([], {**self.facts, key: value})["status"], "hold")

    def test_empty_rules_alone_never_clear_upload(self):
        result = r.assess([], {})
        self.assertEqual(result["status"], "hold")
        self.assertFalse(result["upload_authorized"])

    def test_all_reported_conditions_do_not_attest_live_account(self):
        result = r.assess([], self.facts)
        self.assertEqual(result["status"], "reported-preflight-conditions-met")
        self.assertFalse(result["live_account_verified"])
        self.assertFalse(result["retention_verified"])
        self.assertFalse(result["upload_authorized"])

    def test_overlaps_combine_minimum_for_each_property(self):
        rules = [{"fileNamePrefix": "", r.HIDE: 100}, {"fileNamePrefix": r.PREFIX, r.DELETE: 20},
                 {"fileNamePrefix": r.PREFIX + "part/", r.HIDE: 70}, {"fileNamePrefix": "daily/", r.DELETE: 1}]
        result = r.assess(rules, self.facts)
        self.assertEqual(result["matching_rules"], 3)
        self.assertCountEqual(result["conflicts"], ["automatic-deletion-by-day-90",
                                                    "automatic-deletion-before-owner-release-possible"])

    def test_disjoint_rules_do_not_combine(self):
        rules = [{"fileNamePrefix": r.PREFIX + "a/", r.HIDE: 10},
                 {"fileNamePrefix": r.PREFIX + "b/", r.DELETE: 5}]
        self.assertEqual(r.assess(rules, self.facts)["conflicts"], [])

    def test_budget_exact_boundary_and_insufficient_headroom(self):
        for key, val in (("available_storage_bytes", 99), ("included_retrieval_bytes", 199),
                         ("final_manifest_bytes", False), ("final_manifest_bytes", 0)):
            with self.subTest(key=key, val=val):
                self.assertEqual(r.assess([], {**self.facts, key: val})["status"], "hold")

    def test_ambiguous_or_malformed_inputs(self):
        for rules in (None, [{"prefix": ""}], [{"fileNamePrefix": "", r.DELETE: True}],
                      [{"fileNamePrefix": "", "unknownAction": 1}]):
            with self.assertRaises(ValueError):
                r.assess(rules, self.facts)
        with self.assertRaises(ValueError):
            r.read_json(io.BytesIO(b'{"bucket_private":false,"bucket_private":true}'))


if __name__ == "__main__":
    unittest.main()
