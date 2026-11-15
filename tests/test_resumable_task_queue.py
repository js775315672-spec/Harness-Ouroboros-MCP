"""Resumable queue tests; all CI attestations are offline fixtures."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from resumable_task_queue import new_queue, advance, load, save, next_action, validate, seal

COMMIT = "a" * 40
REPO = "js775315672-spec/Harness-Ouroboros-MCP"
TASKS = [{"id": "task-1", "description": "Create bounded parser"},
         {"id": "task-2", "description": "Add regression tests"}]
CI = f"https://github.com/{REPO}/actions/runs/123"


def evidence(task="task-1", sha="b" * 40, fail=False):
    return {"task_id": task, "source_changed": True, "commit": sha,
            "ci_url": CI, "checks": {"harness": "pass", "ouroboros": "pass",
             "regression": "fail" if fail else "pass", "secrets": "pass"}}


def github_ok(sha):
    return lambda _: {"status": "completed", "conclusion": "success",
                      "html_url": CI, "repository": {"full_name": REPO},
                      "event": "push", "head_sha": sha, "name": "Harness safety checks",
                      "path": ".github/workflows/harness.yml"}


class ResumableQueueTests(unittest.TestCase):
    def test_bootstrap_and_restart_with_no_claimed_execution(self):
        state = new_queue(TASKS, REPO, COMMIT)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "queue.json"
            save(p, state)
            restored = load(p)
            self.assertEqual(restored, state)
            self.assertEqual(next_action(restored)["decision"], "await_external_executor")
            self.assertFalse(next_action(restored)["autonomous_coding_connected"])
            with self.assertRaises(ValueError):
                save(p, state)

    def test_success_requires_github_attestation_and_moves_to_next_task(self):
        state = new_queue(TASKS, REPO, COMMIT)
        with self.assertRaises(ValueError):
            advance(state, evidence(), fetch=lambda _: {"status": "completed", "conclusion": "failure"})
        with self.assertRaises(ValueError):
            advance(state, evidence(), fetch=lambda _: dict(github_ok("b" * 40)("unused"), name="Another workflow"))
        after = advance(state, evidence(), fetch=github_ok("b" * 40))
        self.assertEqual(after["index"], 1)
        self.assertEqual(after["controller"]["cycle"], 2)
        self.assertEqual(after["last_commit"], "b" * 40)
        self.assertTrue(after["events"][0]["attested"])
        with self.assertRaises(ValueError):
            advance(after, evidence("task-2", "b" * 40), fetch=github_ok("b" * 40))
        final = advance(after, evidence("task-2", "c" * 40), fetch=github_ok("c" * 40))
        self.assertEqual(final["index"], 2)
        self.assertEqual(next_action(final)["decision"], "human_review")
        self.assertFalse(next_action(final)["merge_authorized"])

    def test_failed_checks_request_fix_but_do_not_advance(self):
        state = new_queue(TASKS, REPO, COMMIT)
        after = advance(state, evidence(fail=True), fetch=lambda _: self.fail("no attestation for failure"))
        self.assertEqual(after["index"], 0)
        self.assertEqual(after["controller"]["attempt"], 2)
        self.assertFalse(after["events"][0]["attested"])
        self.assertEqual(after["events"][0]["decision"], "request_external_fix")

    def test_checkpoint_integrity_replay_and_wrong_task(self):
        state = new_queue(TASKS, REPO, COMMIT)
        with self.assertRaises(ValueError):
            advance(state, evidence("task-2"), fetch=github_ok("b" * 40))
        with self.assertRaises(ValueError):
            advance(state, evidence(sha=COMMIT), fetch=github_ok(COMMIT))
        with self.assertRaises(ValueError):
            advance(state, dict(evidence(), ci_url="https://github.com/other/repo/actions/runs/123"), fetch=github_ok("b" * 40))
        bad = dict(state)
        bad["index"] = 1
        with self.assertRaises(ValueError):
            validate(bad)

    def test_atomic_checkpoint_cas_and_tamper(self):
        state = new_queue(TASKS, REPO, COMMIT)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "queue.json"
            save(p, state)
            newer = advance(state, evidence(), fetch=github_ok("b" * 40))
            save(p, newer, expected_integrity=state["integrity"])
            with self.assertRaises(ValueError):
                save(p, newer, expected_integrity=state["integrity"])
            doc = json.loads(p.read_text())
            doc["index"] = 0
            p.write_text(json.dumps(doc))
            with self.assertRaises(ValueError):
                load(p)

    def test_restricted_size_schema_and_symlinks(self):
        with self.assertRaises(ValueError):
            new_queue(TASKS * 20, REPO, COMMIT)
        with self.assertRaises(ValueError):
            new_queue([TASKS[0], TASKS[0]], REPO, COMMIT)
        with self.assertRaises(ValueError):
            new_queue([{"id": "../unsafe", "description": "x"}], REPO, COMMIT)
        with tempfile.TemporaryDirectory() as d:
            real = Path(d) / "real.json"
            link = Path(d) / "alias.json"
            save(real, new_queue(TASKS, REPO, COMMIT))
            link.symlink_to(real)
            with self.assertRaises(ValueError):
                load(link)
            with self.assertRaises(ValueError):
                save(link, new_queue(TASKS, REPO, COMMIT))


if __name__ == "__main__":
    unittest.main()
