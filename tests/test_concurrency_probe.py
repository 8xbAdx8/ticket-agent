import unittest
from target.concurrency_probe import probe,SCENARIOS


class ConcurrentOrderTests(unittest.TestCase):
    def test_all_seven_normal_scenarios(self):
        for name in SCENARIOS:
            with self.subTest(scenario=name):
                r=probe(name)
                self.assertEqual(r["judgement"]["test_verdict"],"pass")
                self.assertTrue(r["resources_cleaned"])
                self.assertFalse(r["judgement"]["dimensions"]["platform_defect_detected"])

    def test_two_request_mutation_is_detected(self):
        r=probe(mutant=True)
        self.assertEqual(r["judgement"]["actual_behavior"]["orders"],2)
        self.assertTrue(r["judgement"]["dimensions"]["platform_defect_detected"])
        self.assertEqual(r["judgement"]["quality_verdict"],"fail")
        self.assertEqual(r["judgement"]["test_verdict"],"pass")
        self.assertTrue(r["database_isolation"]["source_data_unchanged_in_mutant"])

    def test_multiple_request_mutation_repeatable_without_sleeps(self):
        for _ in range(3):
            r=probe("same_lock_many",mutant=True)
            self.assertEqual(r["judgement"]["actual_behavior"]["orders"],4)
            self.assertEqual(r["judgement"]["test_verdict"],"pass")
            self.assertTrue(r["resources_cleaned"])

    def test_different_locks_do_not_get_global_idempotency_key(self):
        r=probe("different_locks",mutant=True)
        self.assertEqual(r["judgement"]["actual_behavior"]["orders"],4)
        self.assertFalse(r["judgement"]["dimensions"]["platform_defect_detected"])
        self.assertFalse(r["concurrency"]["application_global_mutex"])

    def test_bounds_and_invalid_scenarios_rejected(self):
        for workers in (0,1,9,True):
            with self.assertRaises(ValueError):probe(workers=workers)
        with self.assertRaises(ValueError):probe("expired_lock",mutant=True)
