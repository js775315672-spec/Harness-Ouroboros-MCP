import unittest
from scripts.oril_slot3_public_cycle_trend_audit import audit

def row(campaign="a", cycle=1, duration=102):
    return dict(campaign=campaign, cycle=cycle, task_id="public-addition",
                group_digest="digest", model_revision="qwen-rev",
                duration_s=duration, baseline_correct=11, candidate_correct=20,
                n_groups=30, input_tokens_base=1860,
                input_tokens_candidate=1020,
                source_url="https://github.com/example/repo/actions/runs/1")

class AuditTests(unittest.TestCase):
    def test_median_and_fail_closed(self):
        rows = [row("a", 1, 127), row("a", 2, 102), row("a", 3, 106),
                row("b", 1, 98), row("b", 2, 102), row("b", 3, 101)]
        result = audit(rows)
        self.assertEqual(result["duration_median_s"], 102)
        self.assertEqual(result["n"], 6)
        self.assertFalse(result["promotion_allowed"])
        self.assertIsNone(result["heldout_quality_change"])
    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            audit([row(), row()])
    def test_bad_count_rejected(self):
        r = row(); r["candidate_correct"] = 31
        with self.assertRaises(ValueError): audit([r])
    def test_boolean_number_rejected(self):
        r = row(); r["duration_s"] = True
        with self.assertRaises(ValueError): audit([r])
    def test_missing_provenance_rejected(self):
        r = row(); r["source_url"] = ""
        with self.assertRaises(ValueError): audit([r])
    def test_incomparable_not_aggregated_as_speed_gain(self):
        a, b = row(), row("b")
        b["group_digest"] = "different"
        result = audit([a,b])
        self.assertFalse(result["comparable_task_environment"])
        self.assertEqual(result["speed_trend"], "판단불가")
    def test_empty_rejected(self):
        with self.assertRaises(ValueError): audit([])
    def test_no_negative_duration(self):
        r = row(); r["duration_s"] = -1
        with self.assertRaises(ValueError): audit([r])
if __name__ == "__main__":
    unittest.main()
