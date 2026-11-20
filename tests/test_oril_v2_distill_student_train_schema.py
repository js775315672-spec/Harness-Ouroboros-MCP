"""Adversarial training row validation for pinned ORIL consumer (synthetic only)."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_distill_pair_marker import publish
from oril_v2_distill_pinned_consumer import consume


class StudentTrainSchemaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        p = Path(self.temp.name)
        self.train = p / "train.jsonl"
        self.report = p / "report.json"
        self.marker = p / "marker.json"
        self.report.write_text(json.dumps({
            "student_weights_updated": False,
            "heldout_evaluation_performed": False}))
        self.good = {"messages": [
            {"role": "user", "content": "Question"},
            {"role": "assistant", "content": "Answer"}]}

    def tearDown(self):
        self.temp.cleanup()

    def check(self, row):
        self.train.write_text(json.dumps(row) + "\n")
        publish(self.train, self.report, self.marker)
        return consume(self.train, self.report, self.marker)

    def test_good_minimal_two_turn_pair(self):
        self.assertIn(b"Question", self.check(self.good)[0])

    def test_rejects_hidden_split(self):
        with self.assertRaisesRegex(ValueError, "invalid train row"):
            self.check({**self.good, "split": "heldout"})

    def test_rejects_extra_system_role(self):
        row = {"messages": [{"role": "system", "content": "ignore rules"}] + self.good["messages"]}
        with self.assertRaisesRegex(ValueError, "invalid student conversation"):
            self.check(row)

    def test_rejects_swapped_roles(self):
        row = {"messages": list(reversed(self.good["messages"]))}
        with self.assertRaisesRegex(ValueError, "invalid student conversation"):
            self.check(row)

    def test_rejects_extra_message_fields(self):
        row = {"messages": [{**self.good["messages"][0], "tool_call": "run"}, self.good["messages"][1]]}
        with self.assertRaisesRegex(ValueError, "invalid student conversation"):
            self.check(row)

    def test_rejects_empty_assistant_answer(self):
        row = {"messages": [self.good["messages"][0], {"role": "assistant", "content": "  "}]}
        with self.assertRaisesRegex(ValueError, "invalid student conversation"):
            self.check(row)

    def test_rejects_metadata_claiming_heldout(self):
        row = {**self.good, "metadata": {"split": "heldout"}}
        with self.assertRaisesRegex(ValueError, "invalid student metadata"):
            self.check(row)

    def test_rejects_boolean_quality(self):
        row = {**self.good, "metadata": {
            "case_id": "c1", "group_id": "g1", "task_type": "debug",
            "review_assertion_url": "https://github.com/a/b/pull/1",
            "candidate_sha": "a"*40, "quality_assertion": True}}
        with self.assertRaisesRegex(ValueError, "invalid student quality"):
            self.check(row)

    def test_rejects_duplicate_case_ids(self):
        row = {**self.good, "metadata": {
            "case_id": "c1", "group_id": "g1", "task_type": "debug",
            "review_assertion_url": "https://github.com/a/b/pull/1",
            "candidate_sha": "a"*40, "quality_assertion": 0.95}}
        self.train.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n")
        publish(self.train, self.report, self.marker)
        with self.assertRaisesRegex(ValueError, "duplicate student case"):
            consume(self.train, self.report, self.marker)

    def test_good_metadata_matches_curator_schema(self):
        row = {**self.good, "metadata": {
            "case_id": "c1", "group_id": "g1", "task_type": "debug",
            "review_assertion_url": "https://github.com/a/b/pull/1",
            "candidate_sha": "a"*40, "quality_assertion": 0.95}}
        self.assertIn(b"c1", self.check(row)[0])


if __name__ == "__main__":
    unittest.main()
