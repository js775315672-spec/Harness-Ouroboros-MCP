"""Safety regression for independent DEV-only 12-cycle runner."""
import sys
import tempfile
import unittest
from pathlib import Path
from agent.dev_cycle_12 import run

OK = [sys.executable, "-c", "print('receipt')"]
BAD = [sys.executable, "-c", "raise SystemExit(2)"]

class DevCycle12Tests(unittest.TestCase):
    def test_bounded_success_and_idempotent_resume(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "state.json"
            first = run(p, "Cerberus", OK, OK, max_cycles=3, budget_seconds=60)
            self.assertEqual(first["status"], "complete")
            self.assertEqual(len(first["cycles"]), 3)
            self.assertEqual(len(run(p, "Cerberus", OK, OK, 3, 60)["cycles"]), 3)
            self.assertEqual(len({c["operation_key"] for c in first["cycles"]}), 3)
            with self.assertRaises(RuntimeError):
                run(p, "Fenrir", OK, OK, 3, 60)

    def test_verifier_failure_keeps_pending_and_stops(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "state.json"
            state = run(p, "Ouroboros", OK, BAD, max_cycles=12, budget_seconds=60)
            self.assertEqual(state["status"], "failed")
            self.assertEqual(len(state["cycles"]), 0)
            self.assertEqual(state["pending"]["cycle"], 1)
            self.assertEqual(len(run(p, "Ouroboros", OK, BAD, 12, 60)["cycles"]), 0)

    def test_ambiguous_pending_never_retries(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "state.json"
            state = run(p, "Fenrir", BAD, OK, 12, 60)
            state["status"] = "ready"
            import json
            p.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "ambiguous pending"):
                run(p, "Fenrir", BAD, OK, 12, 60)

    def test_reject_invalid_bounds(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                run(Path(d)/"x", "Ouroboros", OK, OK, 13, 60)

if __name__ == "__main__":
    unittest.main()
