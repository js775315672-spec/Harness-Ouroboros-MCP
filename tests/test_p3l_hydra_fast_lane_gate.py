"""Offline Hydra admission tests: never execute a model or mutate checkout."""
import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from p3l_hydra_fast_lane_gate import SCHEMA, select_lanes

HEAD = "a" * 40
PROOF = "b" * 64


def item(key, state="pending", deps=None, paths=None, evidence_sha=None):
    return {"key": key, "base_sha": HEAD, "state": state, "deps": deps or [],
            "paths": paths or [f"scripts/{key}.py"],
            "evidence_sha": PROOF if state == "passed" else evidence_sha}


def plan(*tasks, max_parallel=2):
    return {"schema": SCHEMA, "head_sha": HEAD, "max_parallel": max_parallel, "tasks": list(tasks)}


class HydraFastLaneGateTests(unittest.TestCase):
    def test_fifo_nonconflicting_and_dependency_ready(self):
        data = plan(item("parent", "passed"),
                    item("w06", deps=["parent"], paths=["scripts/ledger.py"]),
                    item("w03", paths=["tests/diagnostics.py"]),
                    item("w05", paths=["scripts/ledger.py"]))
        before = copy.deepcopy(data)
        output = select_lanes(data)
        self.assertEqual(output["eligible"], ["w06", "w03"])
        self.assertEqual(data, before)
        self.assertFalse(output["ci_attested"])
        self.assertFalse(output["lease_acquired"])
        self.assertFalse(output["merge_authorized"])
        self.assertEqual(output["model_calls"], 0)

    def test_running_lane_blocks_overlapping_path(self):
        output = select_lanes(plan(item("running", "running", paths=["scripts/ledger.py"]),
                                   item("w06", paths=["scripts/ledger.py"]),
                                   item("w05", paths=["tests/replay.py"])))
        self.assertEqual(output["eligible"], ["w05"])

    def test_blocked_parent_never_unlocks_child(self):
        output = select_lanes(plan(item("w06", "failed"), item("w05", deps=["w06"])))
        self.assertEqual(output["eligible"], [])

    def test_duplicate_event_key_and_bad_dependencies_rejected(self):
        scenarios = (
            plan(item("same"), item("same")),
            plan(item("child", deps=["missing"])),
            plan(item("child", deps=["child"])),
            plan(item("a", deps=["b"]), item("b", deps=["a"])),
            plan(item("a", deps=["b", "b"]), item("b", "passed")),
        )
        for bad in scenarios:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    select_lanes(bad)

    def test_stale_head_and_malformed_success_receipt_rejected(self):
        a = item("a")
        a["base_sha"] = "c" * 40
        b = item("b", "passed")
        b["evidence_sha"] = True
        c = item("c", "pending", evidence_sha=PROOF)
        for bad in (plan(a), plan(b), plan(c)):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    select_lanes(bad)

    def test_paths_and_parallel_limits_rejected(self):
        for path in ("../secret", "/tmp/leak", "scripts/../../x", "", "a//b"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    select_lanes(plan(item("bad", paths=[path])))
        for limit in (0, 5, True, 1.0):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    select_lanes(plan(item("ok"), max_parallel=limit))

    def test_no_auto_completion_claim_from_digest(self):
        out = select_lanes(plan(item("w06")))
        self.assertEqual(len(out["input_sha256"]), 64)
        self.assertFalse(out["model_code_executed"])
        self.assertFalse(out["promotion_authorized"])
        self.assertEqual(out["eligible"], ["w06"])


if __name__ == "__main__":
    unittest.main()
