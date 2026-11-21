"""Standard-library smoke and invariant tests for the ouroboros local memory."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "evolution_context_ouroboros", ROOT / "scripts/evolution_context.py"
)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

class IndependentContextTests(unittest.TestCase):
    def test_real_snapshot_is_valid(self):
        snapshot, rows = mod.load_snapshot(ROOT)
        self.assertEqual(snapshot["agent_id"], "ouroboros")
        self.assertIsInstance(rows, list)

    def test_rejects_other_agent_identity(self):
        snapshot, _ = mod.load_snapshot(ROOT)
        invalid = deepcopy(snapshot)
        invalid["agent_id"] = "another-agent"
        with self.assertRaisesRegex(ValueError, "identity"):
            mod.validate_state(invalid)

    def test_rejects_unproved_gain(self):
        snapshot, _ = mod.load_snapshot(ROOT)
        invalid = deepcopy(snapshot)
        invalid["last_verified_independent_gain"] = {"gain": 0.2}
        invalid["last_verified_cycle"] = "self-001"
        with self.assertRaisesRegex(ValueError, "independent evidence"):
            mod.validate_state(invalid)

    def test_ledger_missing_is_allowed_before_first_experiment(self):
        self.assertEqual(mod.read_ledger(ROOT / "_nonexistent_ledger_file.jsonl"), [])

if __name__ == "__main__":
    unittest.main()
