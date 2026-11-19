"""Replay run-credit invariants for campaign history."""
from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from p3l_hydra_cycle_memory import select


class CycleMemoryTests(unittest.TestCase):
    def test_committed_history_is_reusable(self):
        history = json.loads(Path(__file__).with_name("hydra_cycle_history_fixture.json").read_bytes())
        self.assertEqual(len(select(history, "")), 3)

    def test_repeat_run_cannot_be_credited_as_a_new_cycle(self):
        history = json.loads(Path(__file__).with_name("hydra_cycle_history_fixture.json").read_bytes())
        history["cycles"].append({**history["cycles"][0], "cycle": 4})
        with self.assertRaisesRegex(ValueError, "cycle run already credited"):
            select(history, "")
