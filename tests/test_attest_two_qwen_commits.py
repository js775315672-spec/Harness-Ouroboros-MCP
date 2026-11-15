"""Offline adversarial tests of commit+CI evidence before Ouroboros queue progress."""
import base64
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from attest_two_qwen_commits import (
    attest, API, BASE, COMMITS, RUN_IDS, FILE, TEST, REPO,
)

ORIG = (ROOT / "scripts/feedback_controller.py").read_text(encoding="utf-8")
ARCHIVE1 = json.loads((ROOT / "proposals/feedback_cycle_guard_7b.json").read_text())
ARCHIVE2 = json.loads((ROOT / "proposals/two_qwen_7b_patches_v1.json").read_text())
BASE_GUARD = '    if not isinstance(proposal,dict) or proposal.get("decision")!="propose":'
LOG_GUARD = ('        if status not in ("pass","fail") or not isinstance(log,str) '
             'or len(log)>MAX_LOG_CHARS:')
FIRST = ORIG.replace(BASE_GUARD + "\n", ARCHIVE1["candidate_line"] + "\n", 1)
SECOND = FIRST.replace(LOG_GUARD + "\n", ARCHIVE2["second_line"] + "\n", 1)


def fixture():
    responses = {}
    for i, (sha, run_id, source) in enumerate(zip(COMMITS, RUN_IDS, (FIRST, SECOND))):
        responses[API + "/commits/" + sha] = {
            "sha": sha,
            "parents": [{"sha": BASE if i == 0 else COMMITS[0]}],
            "files": [
                {"filename": FILE, "status": "added" if i == 0 else "modified"},
                {"filename": TEST, "status": "added" if i == 0 else "modified"},
            ],
        }
        responses[API + "/contents/" + FILE + "?ref=" + sha] = {
            "type": "file", "encoding": "base64",
            "content": base64.b64encode(source.encode("utf-8")).decode("ascii"),
        }
        responses[API + "/actions/runs/" + str(run_id)] = {
            "name": "Harness safety checks",
            "path": ".github/workflows/harness.yml",
            "status": "completed", "conclusion": "success",
            "head_sha": sha, "event": "pull_request",
            "html_url": f"https://github.com/{REPO}/actions/runs/{run_id}",
            "repository": {"full_name": REPO},
            "pull_requests": [{"head": {"sha": sha}}],
        }
    return responses


class CommitAttestationTests(unittest.TestCase):
    def test_two_distinct_commits_really_advance_queue(self):
        responses = fixture()
        queue, receipt = attest(ROOT, fetch=lambda url: copy.deepcopy(responses[url]))
        self.assertEqual(queue["index"], 2)
        self.assertEqual(queue["generation"], 2)
        self.assertEqual(queue["last_commit"], COMMITS[1])
        self.assertEqual(queue["controller"]["phase"], "stopped")
        self.assertEqual([row["task_id"] for row in queue["events"]],
                         ["feedback_cycle_guard", "feedback_log_control_guard"])
        self.assertEqual(receipt["completed_tasks"], 2)
        self.assertEqual(len(receipt["workflows"]), 2)
        self.assertFalse(receipt["merge_authorized"])
        self.assertFalse(receipt["autonomous_worker_implemented"])

    def test_first_ci_failed_stops_before_any_credit(self):
        responses = fixture()
        responses[API + "/actions/runs/" + str(RUN_IDS[0])]["conclusion"] = "failure"
        with self.assertRaises(ValueError):
            attest(ROOT, fetch=lambda url: responses[url])

    def test_wrong_second_ci_head_or_pr_head_rejected(self):
        for key in ("head_sha", "pull_requests"):
            responses = fixture()
            run = responses[API + "/actions/runs/" + str(RUN_IDS[1])]
            run[key] = "0" * 40 if key == "head_sha" else [{"head":{"sha": "0" * 40}}]
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    attest(ROOT, fetch=lambda url: responses[url])

    def test_chained_commit_parentage_cannot_be_rewritten(self):
        responses = fixture()
        responses[API + "/commits/" + COMMITS[1]]["parents"] = [{"sha": BASE}]
        with self.assertRaises(ValueError):
            attest(ROOT, fetch=lambda url: responses[url])

    def test_second_commit_must_really_change_exact_code(self):
        responses = fixture()
        content = responses[API + "/contents/" + FILE + "?ref=" + COMMITS[1]]
        content["content"] = base64.b64encode(FIRST.encode()).decode()
        with self.assertRaises(ValueError):
            attest(ROOT, fetch=lambda url: responses[url])

    def test_no_extra_source_changes_accepted(self):
        responses = fixture()
        responses[API + "/commits/" + COMMITS[1]]["files"].append({
            "filename": ".github/workflows/harness.yml", "status": "modified"})
        with self.assertRaises(ValueError):
            attest(ROOT, fetch=lambda url: responses[url])

    def test_ci_workflow_must_be_original_harness(self):
        responses = fixture()
        responses[API + "/actions/runs/" + str(RUN_IDS[0])]["path"] = "other.yml"
        with self.assertRaises(ValueError):
            attest(ROOT, fetch=lambda url: responses[url])

    def test_legacy_original_does_not_get_rewritten(self):
        responses = fixture()
        attest(ROOT, fetch=lambda url: responses[url])
        self.assertEqual(
            (ROOT / "scripts/feedback_controller.py").read_text(encoding="utf-8"), ORIG)


if __name__ == "__main__":
    unittest.main()
