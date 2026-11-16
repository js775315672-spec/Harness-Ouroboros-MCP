"""P3a FROZEN unseen regression oracle for REAL scripts/sandbox_policy.py.

Not included in the Qwen prompt. The original checked-in policy is expected
to fail security cases about caller-owned dictionary aliasing and subclasses
that spoof equality/inequality to bypass contents:read.
"""
import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from sandbox_policy import policy
from task_selector import select

BRANCH="agent/cycle-1-baseline"

class SpoofInequality(dict):
    def __ne__(self, other):
        return False

class SpoofEquality(dict):
    def __eq__(self, other):
        return True
    def __ne__(self, other):
        return False

class FrozenSandboxPolicySecurity(unittest.TestCase):
    def test_caller_owned_input_is_not_exposed_in_output(self):
        supplied={"contents":"read"}
        result=policy(select(), BRANCH, supplied)
        self.assertIsNot(result["github_token_permissions"], supplied)

    def test_subsequent_caller_mutation_cannot_escalate_verified_permissions(self):
        supplied={"contents":"read"}
        result=policy(select(), BRANCH, supplied)
        supplied["contents"]="write"
        self.assertEqual(result["github_token_permissions"], {"contents":"read"})
        self.assertFalse(result["execution_enabled"])

    def test_returned_permissions_not_aliased_back_to_caller(self):
        supplied={"contents":"read"}
        result=policy(select(), BRANCH, supplied)
        result["github_token_permissions"]["contents"]="write"
        self.assertEqual(supplied, {"contents":"read"})

    def test_spoofed_comparison_cannot_accept_write_permission(self):
        with self.assertRaises(ValueError):
            policy(select(), BRANCH, SpoofInequality({"contents":"write"}))

    def test_spoofed_comparison_cannot_accept_extra_scope(self):
        with self.assertRaises(ValueError):
            policy(select(), BRANCH, SpoofEquality(
                {"contents":"read","pull-requests":"write"}))

    def test_even_harmless_custom_mapping_subclass_is_rejected(self):
        with self.assertRaises(ValueError):
            policy(select(), BRANCH, SpoofInequality({"contents":"read"}))

    def test_builtin_read_only_input_works_without_capability_upgrade(self):
        r=policy(select(), BRANCH, {"contents":"read"})
        self.assertEqual(r["github_token_permissions"], {"contents":"read"})
        self.assertIs(r["checkout_persist_credentials"], False)
        self.assertIs(r["shell_execution_allowed"], False)
        self.assertIs(r["network_writes_allowed"], False)
        self.assertIs(r["human_merge_approval_required"], True)

    def test_default_read_only_value_is_independent_between_invocations(self):
        a=policy(select(), BRANCH)
        b=policy(select(), BRANCH)
        self.assertIsNot(a["github_token_permissions"], b["github_token_permissions"])
        a["github_token_permissions"]["contents"]="write"
        self.assertEqual(b["github_token_permissions"], {"contents":"read"})

    def test_invalid_regular_mapping_shapes_still_fail_closed(self):
        for supplied in ({},{"contents":"write"},{"contents":"READ"},
                         {"contents":"read","actions":"write"},None,[],False):
            if supplied is None:
                continue  # None explicitly requests the secure default.
            with self.subTest(supplied=repr(supplied)):
                with self.assertRaises(ValueError):
                    policy(select(), BRANCH, supplied)

    def test_valid_handoff_proposal_not_mutated(self):
        proposal=select()
        before=copy.deepcopy(proposal)
        result=policy(proposal,BRANCH,{"contents":"read"})
        self.assertEqual(proposal,before)
        self.assertEqual(result["cycle"],1)
        self.assertEqual(result["isolation_status"],"policy_only_not_a_sandbox")
