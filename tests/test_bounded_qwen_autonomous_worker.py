"""Offline adversarial tests for a bounded fresh-model two-task worker."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from bounded_qwen_autonomous_worker import (
    TASKS, parse, apply, initial, load, run, verify, original, store,
)

COMMIT = "a" * 40
ANSWERS = ("chr(13) in log", "chr(127) in log")


class FakeModel:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.prompts = []
    def generate(self, prompt):
        self.prompts.append(prompt)
        return next(self.outputs)


def fake_docker(root, before, after, index):
    assert "chr(" + str(TASKS[index][1]) + ") in log" in after
    assert after != before
    return True


class WorkerTests(unittest.TestCase):
    def test_scoped_model_expressions_reject_arbitrary_code(self):
        self.assertEqual(parse(ANSWERS[0], 13), ANSWERS[0])
        self.assertEqual(parse(ANSWERS[1], 127), ANSWERS[1])
        self.assertEqual(parse(chr(96)+ANSWERS[0]+chr(96), 13), ANSWERS[0])
        bad = (
            "chr(27) in log", "chr(True) in log", "chr(13 + 0) in log",
            "chr(13) in other", "other(13) in log", "chr(13) not in log",
            "chr(13) in log or True", "__import__('os').system('id')",
            "chr(13) in log\nprint(1)", "chr(13) in log" + chr(0),
            chr(27) + "[31m", "if True: pass", "chr(13) in log or chr(127) in log",
        )
        for sample in bad:
            with self.subTest(sample=repr(sample)[:50]):
                with self.assertRaises(ValueError):
                    parse(sample, 13)

    def test_distinct_guards_are_ast_scoped_and_ordered(self):
        first, _ = original(ROOT)
        after_a = apply(first, ANSWERS[0], 0)
        after_b = apply(after_a, ANSWERS[1], 1)
        self.assertIn(ANSWERS[0], after_a)
        self.assertIn(ANSWERS[1], after_b)
        self.assertNotIn(ANSWERS[1], after_a)
        with self.assertRaises(ValueError):
            apply(first, ANSWERS[1], 1)
        self.assertEqual((ROOT / "scripts/feedback_controller_verified.py").read_text(), first)

    def test_two_fresh_calls_with_checkpoint_and_separate_restore(self):
        model = FakeModel(ANSWERS)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queue.json"
            state = run(ROOT, COMMIT, model, path, compare=fake_docker)
            self.assertEqual(state["state"], "complete")
            self.assertEqual(len(model.prompts), 2)
            self.assertEqual(state["completed_tasks"], 2)
            self.assertFalse(state["merge_authorized"])
            self.assertTrue(state["human_review_required"])
            self.assertEqual([s["task"] for s in state["steps"]],
                             [task[0] for task in TASKS])
            restored = load(ROOT, path, COMMIT)
            self.assertEqual(restored, state)
            result = verify(ROOT, path, COMMIT, compare=fake_docker)
            self.assertEqual(result["status"], "fresh_two_model_patches_replayed")
            self.assertEqual(result["model_calls"], 2)
            self.assertEqual(result["queue_ci_attested"], 0)
            self.assertFalse(result["merge_authorized"])
            self.assertEqual(run(ROOT, COMMIT, FakeModel([]), path, resume=True,
                                 compare=fake_docker), state)

    def test_checkpoint_survives_failed_second_task_and_can_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queue.json"
            def decline_second(root, old, new, index):
                return index == 0
            model = FakeModel([ANSWERS[0], ANSWERS[1], ANSWERS[1], ANSWERS[1]])
            state = run(ROOT, COMMIT, model, path, compare=decline_second)
            self.assertEqual(state["state"], "blocked")
            self.assertEqual(state["completed_tasks"], 1)
            self.assertEqual(len(state["attempts"]), 4)
            with self.assertRaises(ValueError):
                verify(ROOT, path, COMMIT, compare=fake_docker)
            self.assertEqual(run(ROOT, COMMIT, FakeModel([]), path, resume=True,
                                 compare=fake_docker)["completed_tasks"], 1)

    def test_tampered_checkpoint_and_wrong_sha_cannot_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queue.json"
            state = initial(ROOT, COMMIT)
            store(path, state)
            with self.assertRaises(ValueError):
                load(ROOT, path, "b" * 40)
            forged = json.loads(path.read_text())
            forged["completed_tasks"] = 2
            path.write_text(json.dumps(forged))
            with self.assertRaises(ValueError):
                load(ROOT, path, COMMIT)

    def test_forged_checkpoint_cannot_claim_success_by_resealing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queue.json"
            state = initial(ROOT, COMMIT)
            state["state"] = "complete"
            state["completed_tasks"] = 2
            from bounded_qwen_autonomous_worker import seal
            store(path, seal({k:v for k,v in state.items() if k != "integrity"}))
            with self.assertRaises(ValueError):
                load(ROOT, path, COMMIT)

    def test_bad_model_output_never_earns_task_credit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queue.json"
            bad = FakeModel(["bad", "still bad", "invalid"])
            state = run(ROOT, COMMIT, bad, path, compare=fake_docker)
            self.assertEqual(state["completed_tasks"], 0)
            self.assertEqual(state["state"], "blocked")
            self.assertEqual(len(bad.prompts), 3)
            self.assertEqual(len(state["steps"]), 0)
            self.assertEqual(len(state["attempts"]), 3)
            self.assertFalse(state["merge_authorized"])

    def test_no_silent_overwrite_or_fake_source_modification(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queue.json"
            state = run(ROOT, COMMIT, FakeModel(ANSWERS), path, compare=fake_docker)
            with self.assertRaises(ValueError):
                run(ROOT, COMMIT, FakeModel([]), path, compare=fake_docker)
            self.assertEqual((ROOT / "scripts/feedback_controller_verified.py").read_text(),
                             original(ROOT)[0])


if __name__ == "__main__":
    unittest.main()
