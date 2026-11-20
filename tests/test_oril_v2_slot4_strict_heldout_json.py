"""Fail-closed heldout JSON parser regression: synthetic data only."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_student_real_inference_probe import read_manifest


def record(i):
    return {"case_id": f"c{i}", "group_id": f"g{i}",
            "question": f"question {i}", "expected_answer": f"answer {i}",
            "split": "heldout"}


class StrictHeldoutJsonTests(unittest.TestCase):
    def check_invalid(self, raw, pattern):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "heldout.jsonl"
            path.write_bytes(raw.encode("utf-8"))
            with self.assertRaisesRegex(ValueError, pattern):
                read_manifest(path)

    def test_reject_duplicate_split_key_overwrite(self):
        first = json.dumps(record(0))[:-1] + ',"split":"train"}'
        self.check_invalid(first + "\n" + json.dumps(record(1)), "duplicate JSON key")

    def test_reject_duplicate_group_key_overwrite(self):
        first = json.dumps(record(0))[:-1] + ',"group_id":"other"}'
        self.check_invalid(first + "\n" + json.dumps(record(1)), "duplicate JSON key")

    def test_reject_nan_or_infinity(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                first = json.dumps(record(0))[:-1] + ',"extra":' + value + "}"
                self.check_invalid(first + "\n" + json.dumps(record(1)),
                                   "nonfinite JSON")

    def test_reject_large_manifest_before_inference(self):
        self.check_invalid(" " * (4 * 1024 * 1024 + 1),
                           "exceeds 4 MiB")

    def test_reject_excessive_case_count(self):
        self.check_invalid("\n".join(json.dumps(record(i)) for i in range(1001)),
                           "exceeds 1000 cases")

    def test_reject_oversize_line(self):
        self.check_invalid(json.dumps(record(0)) + " " * 24001 + "\n" + json.dumps(record(1)),
                           "line too large")

    def test_valid_two_groups_preserve_raw_digest(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "heldout.jsonl"
            path.write_text("\n".join(json.dumps(record(i)) for i in range(2)) + "\n")
            rows, digest = read_manifest(path)
            self.assertEqual(len(rows), 2)
            self.assertEqual(len(digest), 64)


if __name__ == "__main__":
    unittest.main()
