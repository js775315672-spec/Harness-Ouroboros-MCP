"""Synthetic negative tests: syntax checks are NOT independent provenance."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_distill_pair_marker import publish
from oril_v2_distill_pinned_consumer import consume


def valid():
    return {
        "messages": [
            {"role": "user", "content": "Check an offline unit test"},
            {"role": "assistant", "content": "Run the isolated test and review its result"},
        ],
        "metadata": {
            "case_id": "c1", "group_id": "g1", "task_type": "debug",
            "review_assertion_url": "https://github.com/a/b/pull/12",
            "candidate_sha": "a" * 40, "quality_assertion": 0.95,
        },
    }


class ProvenanceClaimTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.train, self.report, self.marker = (root / "train.jsonl",
                                                 root / "report.json",
                                                 root / "marker.json")
        self.report.write_text(json.dumps({
            "student_weights_updated": False,
            "heldout_evaluation_performed": False,
        }))

    def tearDown(self):
        self.temp.cleanup()

    def run_pair(self, row):
        # Each synthetic subtest represents a fresh producer transaction.
        # The production publisher deliberately rejects an existing marker.
        self.marker.unlink(missing_ok=True)
        self.train.write_text(json.dumps(row) + "\n")
        publish(self.train, self.report, self.marker)
        return consume(self.train, self.report, self.marker)

    def test_valid_curator_metadata_still_accepted(self):
        data, _ = self.run_pair(valid())
        self.assertIn(b"review_assertion_url", data)

    def test_rejects_non_sha_and_uppercase_sha(self):
        for bad in ("a", "g" * 40, "A" * 40, "a" * 39):
            with self.subTest(bad=bad):
                row = valid()
                row["metadata"]["candidate_sha"] = bad
                with self.assertRaisesRegex(ValueError, "provenance assertion"):
                    self.run_pair(row)

    def test_rejects_non_github_and_lookalike_review_urls(self):
        for bad in ("https://example.org/a/b/pull/12",
                    "https://github.com.evil.org/a/b/pull/12",
                    "http://github.com/a/b/pull/12",
                    "https://github.com/a/b/issues/12",
                    "https://github.com/a/b/pull/12?token=secret",
                    "https://github.com/a/b/pull/12/../../evil"):
            with self.subTest(bad=bad):
                row = valid()
                row["metadata"]["review_assertion_url"] = bad
                with self.assertRaisesRegex(ValueError, "provenance assertion"):
                    self.run_pair(row)

    def test_rejects_control_and_invisible_identifier(self):
        for bad in ("group\nnext", "g\u200b1", "x" * 81, " group"):
            with self.subTest(bad=bad):
                row = valid()
                row["metadata"]["group_id"] = bad
                with self.assertRaisesRegex(ValueError, "student metadata"):
                    self.run_pair(row)

    def test_accepts_actions_review_claim_without_certifying_it(self):
        row = valid()
        row["metadata"]["review_assertion_url"] = (
            "https://github.com/a/b/actions/runs/1234")
        data, _ = self.run_pair(row)
        self.assertIn(b"actions/runs/1234", data)


if __name__ == "__main__":
    unittest.main()
