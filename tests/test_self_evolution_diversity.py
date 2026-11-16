"""P1c offline tests: cloned passing source cannot be counted twice."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import self_evolution_diversity as s

HEAD = "a"*40
CANDIDATE = "b"*64
VARIANT = s.VARIANT


def fixtures():
    reports = []
    replays = []
    for i, lane in enumerate(("01", "02")):
        reports.append({
            "lane": lane, "source_sha": HEAD, "study_variant": VARIANT,
            "model_calls": 1, "ci_attested_patches": 0,
            "checkout_modified": False, "merge_authorized": False,
            "architecture": ["central-state-machine", "event-sourced"][i],
            "contract_sha256": "c"*64, "holdout_sha256": "d"*64,
            "prompt_sha256": ("1" if i == 0 else "2")*64,
            "response_sha256": "e"*64,
            "outcome": "model_candidate_passed",
            "candidate_sha256": CANDIDATE,
            "evaluation": {"status": "model_candidate_passed"},
        })
        replays.append({
            "lane": lane, "status": "candidate_replayed",
            "candidate_passed": True, "candidate_sha256": CANDIDATE,
            "merge_authorized": False,
        })
    return reports, replays


class DiversityTests(unittest.TestCase):
    def case(self, model_change=None, replay_change=None, exception=True):
        m, r = fixtures()
        if model_change:
            model_change(m)
        if replay_change:
            replay_change(r)
        if exception:
            with self.assertRaises(ValueError):
                s.summarize(m, r, HEAD)
        else:
            return s.summarize(m, r, HEAD)

    def test_identical_code_counted_once(self):
        result = self.case(exception=False)
        self.assertEqual(result["model_trials"], 2)
        self.assertEqual(result["cross_runner_replayed_passing_trials"], 2)
        self.assertEqual(result["unique_passing_source_candidates"], 1)
        self.assertEqual(result["duplicate_source_groups"][0]["lanes"],
                         ["01", "02"])
        self.assertFalse(result["architecture_diversity_proven"])
        self.assertEqual(result["recursive_parent_promotions"], 0)

    def test_different_candidate_source_bytes_counted_twice(self):
        result = self.case(
            model_change=lambda m: m[1].update(candidate_sha256="f"*64),
            replay_change=lambda r: r[1].update(candidate_sha256="f"*64),
            exception=False)
        self.assertEqual(result["unique_passing_source_candidates"], 2)
        self.assertTrue(result["distinct_source_bytes_observed"])
        self.assertFalse(result["architecture_diversity_proven"])
        self.assertEqual(result["recursive_parent_promotions"], 0)

    def test_one_failed_candidate_not_promoted(self):
        result = self.case(
            model_change=lambda m: (
                m[1].update(outcome="model_candidate_failed",
                            evaluation={"status":"model_candidate_failed"})),
            replay_change=lambda r: r[1].update(candidate_passed=False),
            exception=False)
        self.assertEqual(result["cross_runner_replayed_passing_trials"], 1)
        self.assertEqual(result["unique_passing_source_candidates"], 1)

    def test_static_rejection_not_a_candidate(self):
        result = self.case(
            model_change=lambda m: m[1].update(
                outcome="static_gate_rejected", candidate_sha256=None,
                evaluation=None),
            replay_change=lambda r: r[1].update(
                status="static_rejection_replayed",
                candidate_passed=False, candidate_sha256=None),
            exception=False)
        self.assertEqual(result["cross_runner_replayed_passing_trials"], 1)

    def test_forged_test_pass_rejected(self):
        self.case(replay_change=lambda r: r[1].update(candidate_passed=False))

    def test_changed_candidate_digest_rejected(self):
        self.case(replay_change=lambda r: r[1].update(candidate_sha256="f"*64))

    def test_no_model_call_rejected(self):
        self.case(model_change=lambda m: m[0].update(model_calls=0))

    def test_unauthorized_merge_rejected(self):
        self.case(model_change=lambda m: m[0].update(merge_authorized=True))

    def test_unauthorized_ci_credit_rejected(self):
        self.case(model_change=lambda m: m[0].update(ci_attested_patches=1))

    def test_unreviewed_commit_rejected(self):
        self.case(model_change=lambda m: m[1].update(source_sha="f"*40))

    def test_variant_mismatch_rejected(self):
        self.case(model_change=lambda m: m[1].update(study_variant="v1"))

    def test_same_prompt_not_architectural_comparison(self):
        self.case(model_change=lambda m: m[1].update(prompt_sha256="1"*64))

    def test_same_architecture_rejected(self):
        self.case(model_change=lambda m: m[1].update(architecture="central-state-machine"))

    def test_missing_lane_rejected(self):
        self.case(model_change=lambda m: m[1].update(lane="03"))

    def test_duplicate_lane_rejected(self):
        self.case(replay_change=lambda r: r[1].update(lane="01"))

    def test_unknown_outcome_rejected(self):
        self.case(model_change=lambda m: m[1].update(outcome="passed_because_green_ci"))

    def test_invalid_review_sha_rejected(self):
        with self.assertRaises(ValueError):
            m, r = fixtures()
            s.summarize(m, r, "bad")

    def test_exactly_two_reports_required(self):
        m, r = fixtures()
        with self.assertRaises(ValueError):
            s.summarize(m[:1], r, HEAD)

    def test_json_duplicate_keys_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/"replay.json"
            path.write_text('{"lane":"01","lane":"02"}')
            with self.assertRaises(ValueError):
                s._read(path)

    def test_json_symlink_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/"actual.json").write_text('{"lane":"01"}')
            (root/"alias.json").symlink_to(root/"actual.json")
            with self.assertRaises(ValueError):
                s._read(root/"alias.json")


if __name__ == "__main__":
    unittest.main()
