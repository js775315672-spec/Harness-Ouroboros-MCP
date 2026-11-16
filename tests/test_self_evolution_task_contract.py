"""Offline, adversarial P1a preflight tests. No model or GitHub credentials."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import self_evolution_task_contract as subject


class TestEightLaneContracts(unittest.TestCase):
    def setUp(self):
        self.config = {
            "schema": 1, "repository": subject.REPOSITORY,
            "target_scope": "self-repository-only",
            "goal": "Develop a safe bounded recoverable auditable self-development cycle",
            "execution_mode": "read-only-infrastructure-smoke",
            "automatic_model_execution": False, "automatic_remote_push": False,
            "automatic_pr_creation": False, "automatic_merge": False,
            "human_approval_required": True, "paid_api_allowed": False,
            "user_provided_secrets_allowed": False, "scheduler_enabled": False,
            "epoch_minutes": 60, "worker_budget_seconds": 3000,
            "checkpoint_interval_minutes": 5, "max_parallel": 8,
            "max_children_per_attested_parent": 8,
            "max_pending_children_per_epoch": 64,
            "max_epochs_without_renewed_approval": 1,
            "frozen_oracle_commands": list(subject.ORACLES),
            "protected_paths": list(subject.PROTECTED),
            "lanes": [{"id":f"{i:02d}",
                       "architecture_key":f"architecture-{i}",
                       "title": "architecture test", "high_level_goal":
                           "Develop a safe bounded recoverable auditable self-development cycle",
                       "hypothesis":f"Different approach {i}",
                       "candidate_source_paths":list(subject.ROOTS),
                       "accept_only_if":subject.REQUIRED_ACCEPTANCE,
                       "worktree_only":True} for i in range(1,9)]}
        self.sha = "a" * 40

    def test_eight_distinct_pinned_manifests(self):
        manifests = subject.build_manifests(self.config, self.sha)
        self.assertEqual([m["lane_id"] for m in manifests], list(subject.LANES))
        self.assertEqual(len({m["contract_sha256"] for m in manifests}), 8)
        self.assertEqual(len({m["frozen_oracle_sha256"] for m in manifests}), 1)
        self.assertTrue(all(m["model_execution_authorized"] is False for m in manifests))
        self.assertEqual(subject.verify_manifests(self.config, self.sha, manifests)
                         ["verified_model_patches"], 0)

    def reject_config(self, mutate):
        config = copy.deepcopy(self.config)
        mutate(config)
        with self.assertRaises(ValueError):
            subject.validate_config(config)

    def test_model_execution_fails_closed(self):
        self.reject_config(lambda c: c.update(automatic_model_execution=True))

    def test_non_boolean_zero_fails_closed(self):
        self.reject_config(lambda c: c.update(automatic_merge=0))

    def test_remote_write_fails_closed(self):
        self.reject_config(lambda c: c.update(automatic_remote_push=True))

    def test_scheduler_fails_closed(self):
        self.reject_config(lambda c: c.update(scheduler_enabled=True))

    def test_oracle_mutation_fails_closed(self):
        self.reject_config(lambda c: c["frozen_oracle_commands"].pop())

    def test_protected_path_mutation_fails_closed(self):
        self.reject_config(lambda c: c["protected_paths"].remove("scripts/governance.py"))

    def test_duplicate_architecture_fails_closed(self):
        self.reject_config(lambda c: c["lanes"][1].update(architecture_key="architecture-1"))

    def test_wrong_goal_fails_closed(self):
        self.reject_config(lambda c: c["lanes"][2].update(high_level_goal="different goal"))

    def test_path_traversal_fails_closed(self):
        self.reject_config(lambda c: c["lanes"][0].update(candidate_source_paths=["../secret/"]))

    def test_weak_acceptance_fails_closed(self):
        self.reject_config(lambda c: c["lanes"][0].update(accept_only_if="green CI"))

    def test_max_parallel_increase_fails_closed(self):
        self.reject_config(lambda c: c.update(max_parallel=64))

    def test_new_unknown_field_fails_closed(self):
        self.reject_config(lambda c: c.update(skip_harness=True))

    def test_wrong_sha_fails_closed(self):
        for invalid in ("A"*40, "abc", "a"*64):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    subject.build_manifests(self.config, invalid)

    def test_aggregate_rejects_false_generated_claim(self):
        m = subject.build_manifests(self.config, self.sha)
        m[0]["source_patch_generated"] = True
        with self.assertRaises(ValueError):
            subject.verify_manifests(self.config, self.sha, m)

    def test_aggregate_rejects_missing_lane(self):
        m = subject.build_manifests(self.config, self.sha)
        with self.assertRaises(ValueError):
            subject.verify_manifests(self.config, self.sha, m[:7])

    def test_aggregate_rejects_duplicate_lane(self):
        m = subject.build_manifests(self.config, self.sha)
        m[7] = m[6]
        with self.assertRaises(ValueError):
            subject.verify_manifests(self.config, self.sha, m)

    def test_load_config_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "real.json").write_text(json.dumps(self.config), encoding="utf-8")
            (p / "alias.json").symlink_to(p / "real.json")
            with self.assertRaises(ValueError):
                subject.load_config(p / "alias.json")

    def test_load_config_allows_valid_json(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "config.json"
            p.write_text(json.dumps(self.config), encoding="utf-8")
            loaded = subject.load_config(p)
            self.assertEqual(len(subject.build_manifests(loaded, self.sha)), 8)

if __name__ == "__main__":
    unittest.main()
