"""Verify the cross-runner rehearsal rejects missing or mismatched state."""
from pathlib import Path
from shutil import copyfile
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from p3l_w04_runner_rehearsal import publish, recover, snapshot_sha, synthetic_inputs


class RunnerRehearsalTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.snapshot = root / "registry.sqlite3"
        self.receiver = root / "downloaded.sqlite3"
        self.inputs = synthetic_inputs("1" * 40, "2" * 40, 123)

    def test_transferred_snapshot_keeps_the_spent_budget(self):
        result = publish(self.snapshot, self.inputs, 123)
        copyfile(self.snapshot, self.receiver)
        resumed = recover(self.receiver, self.inputs, 123, result["snapshot_sha256"])
        self.assertEqual(result["simulated_start_count"], 1)
        self.assertEqual(resumed["recovered_state"], "UNVERIFIED")
        self.assertIs(resumed["duplicate_reservation_blocked"], True)
        self.assertIs(resumed["duplicate_start_blocked"], True)

    def test_changed_snapshot_is_rejected_before_sqlite_opens_it(self):
        result = publish(self.snapshot, self.inputs, 123)
        self.receiver.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "snapshot digest mismatch"):
            recover(self.receiver, self.inputs, 123, result["snapshot_sha256"])
        self.assertEqual(self.receiver.read_bytes(), b"changed")

    def test_matching_digest_cannot_reuse_a_snapshot_from_another_run(self):
        publish(self.snapshot, self.inputs, 123)
        other = synthetic_inputs(self.inputs.base_sha, self.inputs.head_sha, 124)
        original = snapshot_sha(self.snapshot)
        with self.assertRaisesRegex(ValueError, "expected spent slot"):
            recover(self.snapshot, other, 124, original)
        self.assertEqual(snapshot_sha(self.snapshot), original)


if __name__ == "__main__":
    unittest.main()
