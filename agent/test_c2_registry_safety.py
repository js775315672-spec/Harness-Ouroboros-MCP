"""C2 isolation audit: legacy CR pathname and cross-cycle operation identity.

Tests run ONLY against TemporaryDirectory bare Git fixtures. No production
registry, main branch, GitHub merge, or API write is touched.
"""
import importlib.util
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import cycle_registry as r


class C2GitSafety(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="ofc-c2-isolated-")
        self.addCleanup(temp.cleanup)
        self.remote = str(pathlib.Path(temp.name) / "fixture.git")
        r.git("init", "--quiet", "--bare", self.remote)
        self.source = r.git("commit-tree", r.git("mktree", stdin=""),
                            "-m", "fixture main")
        r.git("push", self.remote, self.source + ":refs/heads/main")
        self.first = r.transact(self.remote, "acquire", "initial", 0,
                                self.source)

    def tip(self):
        return r.git("ls-remote", self.remote, r.REF).split()[0]

    def append_tree(self, names):
        state = r.transact(self.remote, "inspect")
        blob = r.git("hash-object", "-w", "--stdin",
                     stdin=json.dumps(state, sort_keys=True) + "\n")
        tree = r.git("mktree", stdin="".join(
            "100644 blob " + blob + "\t" + name + "\n" for name in names))
        previous = self.tip()
        commit = r.git("commit-tree", tree, "-p", previous, "-m",
                       "C2 isolated malformed/legacy tree fixture")
        r.git("push", self.remote, commit + ":" + r.REF)
        return commit

    def test_active_cr_suffixed_file_blocks_inspect_and_acquire(self):
        bad = self.append_tree(["state.json\r"])
        listing = r.git("--git-dir=" + self.remote, "ls-tree", "--name-only", bad)
        self.assertIn("state.json", listing)
        self.assertNotEqual(listing, "state.json")
        for command in ("inspect", "acquire"):
            with self.subTest(command=command):
                with self.assertRaisesRegex(r.Blocked, "noncanonical active registry tree"):
                    r.transact(self.remote, command, "new", 0, self.source)
                self.assertEqual(self.tip(), bad)

    def test_ambiguous_both_canonical_and_cr_file_blocks(self):
        bad = self.append_tree(["state.json", "state.json\r"])
        names = r.git("--git-dir=" + self.remote, "ls-tree", "--name-only", bad)
        self.assertIn("state.json", names)
        self.assertIn("state.json\\r", names)
        with self.assertRaisesRegex(r.Blocked, "noncanonical active registry tree"):
            r.transact(self.remote, "inspect")
        self.assertEqual(self.tip(), bad)

    def test_legacy_parent_is_preserved_but_canonical_current_tip_is_readable(self):
        old = self.append_tree(["state.json\r"])
        # This models a manual, reviewed repair commit on an *isolated* ref.
        # Production restoration always requires a separate human decision.
        blob = r.git("hash-object", "-w", "--stdin",
                     stdin=json.dumps(self.first, sort_keys=True) + "\n")
        fixed_tree = r.git("mktree",
                           stdin="100644 blob " + blob + "\tstate.json\n")
        fixed = r.git("commit-tree", fixed_tree, "-p", old,
                      "-m", "C2 isolated reviewed canonicalization fixture")
        r.git("push", self.remote, fixed + ":" + r.REF)
        self.assertEqual(r.transact(self.remote, "inspect"), self.first)
        legacy = r.git("--git-dir=" + self.remote, "ls-tree",
                       "--name-only", old)
        self.assertNotEqual(legacy, "state.json")
        self.assertEqual(
            r.git("--git-dir=" + self.remote, "ls-tree",
                  "--name-only", fixed), "state.json")

    def test_expired_merge_recovery_refuses_cr_active_tree_before_verifier(self):
        operation = json.dumps(
            {"base_sha": self.source, "operation_id": "c2-merge-001"},
            sort_keys=True)
        r.transact(self.remote, "reserve", "initial", 1, self.source,
                   operation)
        bad = self.append_tree(["state.json\r"])
        merged = r.git("commit-tree", r.git("mktree", stdin=""),
                       "-p", self.source, "-m", "C2 local synthetic merge")
        r.git("push", self.remote, merged + ":refs/heads/main")
        evidence = json.dumps({"merge_commit_sha": merged}, sort_keys=True)
        with patch.object(r, "REMOTE", self.remote), patch.object(
                r, "verify_github_merge", return_value=True) as verifier:
            with self.assertRaisesRegex(r.Blocked, "noncanonical active registry tree"):
                r.recover_merged_pr(self.remote, owner="next",
                                    source=self.source, operation=operation,
                                    evidence=evidence)
            verifier.assert_not_called()
        self.assertEqual(self.tip(), bad)

    def test_reused_operation_name_has_new_cycle_and_fenced_old_owner(self):
        operation = "qwen-public-trial"
        r.transact(self.remote, "reserve", "initial", 1, self.source, operation)
        r.transact(self.remote, "record", "initial", 1, self.source,
                   operation + "=evidence-cycle-one")
        previous = r.transact(self.remote, "complete", "initial", 1, self.source)
        old_tip = self.tip()
        second = r.transact(self.remote, "acquire", "next", 0, self.source)
        self.assertNotEqual(self.first["cycle"], second["cycle"])
        self.assertEqual(second["generation"], 2)
        self.assertEqual(second["results"], {})
        r.transact(self.remote, "reserve", "next", 2, self.source, operation)
        with self.assertRaisesRegex(r.Blocked, "stale lease"):
            r.transact(self.remote, "record", "initial", 1, self.source,
                       operation + "=stale-owner-evidence")
        with self.assertRaisesRegex(r.Blocked, "operation key"):
            r.transact(self.remote, "record", "next", 2, self.source,
                       "wrong-task=evidence")
        self.assertEqual(r.transact(self.remote, "inspect")["pending"], operation)
        r.transact(self.remote, "record", "next", 2, self.source,
                   operation + "=evidence-cycle-two")
        current = r.transact(self.remote, "inspect")
        self.assertEqual(current["results"], {operation: "evidence-cycle-two"})
        old = json.loads(r.git("--git-dir=" + self.remote, "show",
                              old_tip + ":state.json"))
        self.assertEqual(old["results"], {operation: "evidence-cycle-one"})
        self.assertEqual(old["phase"], "complete")
        self.assertEqual(previous["cycle"], self.first["cycle"])


class C2HistoricalAuditRules(unittest.TestCase):
    def setUp(self):
        path = pathlib.Path(__file__).resolve().parent / "audit_operational_history.py"
        spec = importlib.util.spec_from_file_location("ofc_c2_history_audit", path)
        self.audit = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {
                "GITHUB_REPOSITORY": "isolated/c2-fixture",
                "OFC_AGENT": r.AGENT,
                "GITHUB_TOKEN": ""}):
            spec.loader.exec_module(self.audit)

    def synthetic_history(self, second_evidence):
        base = "a" * 40
        def state(cycle, generation, phase, results):
            return {"agent": r.AGENT, "schema": 1, "source": base,
                    "generation": generation, "phase": phase, "cycle": cycle,
                    "pending": None, "results": results, "expires": 0}
        return [
            {"sha": "1" * 40, "path": "state.json",
             "state": state("first", 1, "complete",
                            {"qwen-public-trial": "receipt-cycle-one"})},
            {"sha": "2" * 40, "path": "state.json\r",
             "state": state("second", 2, "open", {})},
            {"sha": "3" * 40, "path": "state.json",
             "state": state("second", 2, "open",
                            {"qwen-public-trial": second_evidence})},
        ]

    def test_legacy_cr_in_history_is_allowed_but_current_tip_is_not(self):
        a = self.audit
        historical = self.synthetic_history("receipt-cycle-two")
        a.check_active_registry_path(historical)
        self.assertEqual(a.errors, [])
        a.check_active_registry_path(historical[:2])
        self.assertTrue(any("noncanonical" in error for error in a.errors))

    def test_reused_name_distinct_evidence_is_separately_identified(self):
        a = self.audit
        summary = a.validate_history(
            self.synthetic_history("receipt-cycle-two"), "a" * 40)
        self.assertEqual(a.errors, [])
        self.assertEqual(summary["cross_cycle_duplicate_receipt_values"], 0)
        self.assertEqual(summary["reused_operation_names_across_cycles"],
                         ["qwen-public-trial"])
        self.assertTrue(any("cycle-qualified" in msg for msg in a.warnings))

    def test_repeated_identical_receipt_across_cycles_is_rejected(self):
        a = self.audit
        summary = a.validate_history(
            self.synthetic_history("receipt-cycle-one"), "a" * 40)
        self.assertEqual(summary["cross_cycle_duplicate_receipt_values"], 1)
        self.assertTrue(any("duplicated across distinct cycles" in err
                            for err in a.errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
