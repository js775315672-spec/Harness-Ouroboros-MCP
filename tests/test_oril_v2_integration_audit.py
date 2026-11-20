"""Regression tests for PR integration readiness: green CI is not promotion."""
import copy
import unittest

from scripts.oril_v2_integration_audit import audit


def record(number=242, base="metrics-parent", branch="metrics-child", sha="a" * 40,
           draft=True, merged_at=None, state="open"):
    return {"number": number, "base": {"ref": base}, "head": {"ref": branch, "sha": sha},
            "draft": draft, "merged_at": merged_at, "state": state}


def fixture():
    parent = record(241, "main", "metrics-parent", "b" * 40)
    child = record()
    run = {"name": "ORIL v2 cycle metrics offline tests", "head_sha": "a" * 40,
           "event": "pull_request", "status": "completed", "conclusion": "success",
           "html_url": "https://github.com/example/repo/actions/runs/123"}
    return {"default_branch": "main", "pull_requests": [parent, child],
            "workflow_runs": [run],
            "required_workflows": {"242": ["ORIL v2 cycle metrics offline tests"]}}


class ReadinessAuditTests(unittest.TestCase):
    def test_stacked_successful_ci_still_blocked(self):
        out = audit(fixture())
        item = out["pull_requests"][1]
        self.assertEqual(item["ci_snapshot_status"], "snapshot_success")
        self.assertIn("unmerged_parent:241", item["blockers"])
        self.assertIn("draft", item["blockers"])
        self.assertFalse(item["merge_approved"])
        self.assertEqual(out["ci_snapshot_success_count"], 1)

    def test_parent_merged_requires_base_update(self):
        data = fixture()
        data["pull_requests"][0]["merged_at"] = "2026-11-20T01:00:00Z"
        item = audit(data)["pull_requests"][1]
        self.assertIn("parent_merged_but_base_not_updated", item["blockers"])
        self.assertIn("non_default_base", item["blockers"])

    def test_exact_sha_required_for_ci(self):
        data = fixture()
        data["workflow_runs"][0]["head_sha"] = "c" * 40
        item = audit(data)["pull_requests"][1]
        self.assertEqual(item["ci_snapshot_status"], "unverified")
        self.assertIn("ci_missing_or_stale", item["blockers"])

    def test_skipped_ci_not_success(self):
        data = fixture()
        data["workflow_runs"][0]["conclusion"] = "skipped"
        self.assertEqual(audit(data)["pull_requests"][1]["ci_snapshot_status"], "unverified")

    def test_in_progress_ci_not_success(self):
        data = fixture()
        data["workflow_runs"][0]["status"] = "in_progress"
        self.assertEqual(audit(data)["pull_requests"][1]["ci_snapshot_status"], "unverified")

    def test_schedule_event_not_a_pr_check(self):
        data = fixture()
        data["workflow_runs"][0]["event"] = "schedule"
        self.assertEqual(audit(data)["pull_requests"][1]["ci_snapshot_status"], "unverified")

    def test_missing_required_workflows_is_unverified(self):
        data = fixture()
        data["required_workflows"] = {}
        self.assertIn("required_ci_unconfigured", audit(data)["pull_requests"][1]["blockers"])

    def test_all_required_workflows_must_pass(self):
        data = fixture()
        data["required_workflows"]["242"].append("separate security scan")
        self.assertEqual(audit(data)["pull_requests"][1]["ci_snapshot_status"], "unverified")

    def test_closed_unmerged_is_not_integrated(self):
        data = fixture()
        data["pull_requests"][1]["state"] = "closed"
        data["pull_requests"][1]["draft"] = False
        self.assertEqual(audit(data)["pull_requests"][1]["stage"], "closed_unmerged")
        self.assertEqual(audit(data)["merged_to_base_count"], 0)

    def test_merged_parent_is_reported_separately(self):
        data = fixture()
        data["pull_requests"][0]["state"] = "closed"
        data["pull_requests"][0]["merged_at"] = "2026-11-20T01:00:00Z"
        self.assertEqual(audit(data)["merged_to_base_count"], 1)

    def test_duplicate_pr_rejected(self):
        data = fixture()
        data["pull_requests"].append(copy.deepcopy(data["pull_requests"][1]))
        with self.assertRaises(ValueError):
            audit(data)

    def test_duplicate_branch_rejected(self):
        data = fixture()
        data["pull_requests"][1]["head"]["ref"] = "metrics-parent"
        with self.assertRaises(ValueError):
            audit(data)

    def test_boolean_pr_number_rejected(self):
        data = fixture()
        data["pull_requests"][1]["number"] = True
        with self.assertRaises(ValueError):
            audit(data)

    def test_invalid_sha_rejected(self):
        data = fixture()
        data["pull_requests"][1]["head"]["sha"] = "z" * 40
        with self.assertRaises(ValueError):
            audit(data)

    def test_run_url_must_be_provided(self):
        data = fixture()
        del data["workflow_runs"][0]["html_url"]
        self.assertEqual(audit(data)["pull_requests"][1]["ci_snapshot_status"], "unverified")

    def test_missing_parent_snapshot_is_a_blocker(self):
        data = fixture()
        data["pull_requests"] = data["pull_requests"][1:]
        self.assertIn("parent_not_in_snapshot", audit(data)["pull_requests"][0]["blockers"])

    def test_untrusted_snapshot_never_claims_ai_gain(self):
        result = audit(fixture())
        self.assertEqual(result["snapshot_authenticity"], "unverified")
        self.assertEqual(result["pull_requests"][1]["independent_model_evaluation"], "unmeasured")
        self.assertFalse(result["pull_requests"][1]["merge_approved"])

    def test_cross_repository_run_rejected_when_identity_supplied(self):
        data = fixture()
        data["repository_full_name"] = "trusted/oril"
        item = audit(data)["pull_requests"][1]
        self.assertEqual(item["ci_snapshot_status"], "unverified")
        self.assertIn("ci_missing_or_stale", item["blockers"])

    def test_same_repository_run_accepted_when_identity_supplied(self):
        data = fixture()
        data["repository_full_name"] = "trusted/oril"
        data["workflow_runs"][0]["html_url"] = "https://github.com/trusted/oril/actions/runs/123"
        self.assertEqual(audit(data)["pull_requests"][1]["ci_snapshot_status"], "snapshot_success")

    def test_repository_prefix_spoof_rejected(self):
        data = fixture()
        data["repository_full_name"] = "trusted/oril"
        data["workflow_runs"][0]["html_url"] = "https://github.com/trusted/oril-evil/actions/runs/123"
        self.assertEqual(audit(data)["pull_requests"][1]["ci_snapshot_status"], "unverified")

    def test_malformed_repository_identity_rejected(self):
        data = fixture()
        data["repository_full_name"] = "https://github.com/trusted/oril"
        with self.assertRaises(ValueError):
            audit(data)


if __name__ == "__main__":
    unittest.main()
