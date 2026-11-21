"""OFC R1 isolated replay, retry and concurrent CAS hardening tests.

Every Git operation runs against a newly created disposable bare repository.
No production registry, main branch, external execution or real merge is used.
"""
import concurrent.futures
import copy
import hashlib
import hmac
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import cycle_registry as r


class R1GlobalIdempotencyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ofc-r1-replay-")
        self.addCleanup(tmp.cleanup)
        self.remote = str(pathlib.Path(tmp.name) / "independent.git")
        r.git("init", "--quiet", "--bare", self.remote)
        self.source = r.git("commit-tree", r.git("mktree", stdin=""),
                            "-m", "R1 isolated baseline")
        r.git("push", self.remote, self.source + ":refs/heads/main")
        self.first = r.transact(self.remote, "acquire", "worker", 0, self.source)
        # Isolated verifier fixture. Never set a production attestation secret.
        self.r2_fixture_key = ("R2-TEST-KEY-ONLY:" + r.AGENT + ":" + "z" * 40)
        fixture = patch.dict(os.environ, {
            "OFC_R2_VERIFIER_KEY": self.r2_fixture_key,
            "OFC_R2_VERIFIER_KEY_ID": "isolated-test-verifier"})
        fixture.start()
        self.addCleanup(fixture.stop)

    def op(self, *, operation="operation-00001", effect="external-effect-00001",
           cycle=None, agent=None, source=None):
        return json.dumps({
            "protocol": r.R1_PROTOCOL, "agent": agent or r.AGENT,
            "cycle_id": cycle or r.transact(self.remote, "inspect")["cycle"],
            "operation_id": operation, "effect_id": effect,
            "source": source or self.source}, sort_keys=True)

    def receipt(self, op, receipt="external-receipt-00001", **overrides):
        intent = json.loads(op)
        value = {k: intent[k] for k in
                 ("agent", "cycle_id", "operation_id", "effect_id", "source")}
        value.update({"protocol": r.R1_RECEIPT, "receipt_id": receipt,
                      "proof": "ISOLATED TEST FIXTURE: no external execution"})
        value.update(overrides)
        message = (b"OFC-R2-RECEIPT-V1\\x00" +
                   r.AGENT.encode("ascii") + b"\\x00" +
                   json.dumps(value, sort_keys=True, ensure_ascii=False,
                              separators=(",", ":")).encode("utf-8"))
        sig = hmac.new(self.r2_fixture_key.encode("utf-8"), message,
                       hashlib.sha256).hexdigest()
        value["attestation"] = {"scheme": "hmac-sha256",
                                "key_id": "isolated-test-verifier",
                                "signature": sig}
        return json.dumps(value, sort_keys=True)

    def tx(self, cmd, *, owner="worker", generation=1, value=""):
        return r.transact(self.remote, cmd, owner, generation, self.source, value)

    def tip(self):
        return r.git("ls-remote", self.remote, r.REF).split()[0]

    def test_cycle_rollover_persists_tombstones_and_fences_replays(self):
        op = self.op()
        self.tx("reserve", value=op)
        self.tx("record", value=op + "=" + self.receipt(op))
        self.tx("complete")
        old_tip = self.tip()
        next_cycle = self.tx("acquire", owner="second", generation=0)
        self.assertNotEqual(next_cycle["cycle"], self.first["cycle"])
        self.assertEqual(next_cycle["results"], {})
        self.assertEqual(next_cycle["r1_guard"]["operations"]["operation-00001"]["status"],
                         "recorded")
        for repeat in [
            self.op(operation="operation-00001", effect="new-effect-00002"),
            self.op(operation="operation-00002", effect="external-effect-00001"),
        ]:
            before = self.tip()
            with self.assertRaisesRegex(r.Blocked, "replay"):
                self.tx("reserve", owner="second", generation=2, value=repeat)
            self.assertEqual(self.tip(), before)
        reused_label = self.op(operation="operation-00002", effect="new-effect-00002")
        self.tx("reserve", owner="second", generation=2, value=reused_label)
        old = json.loads(r.git("--git-dir=" + self.remote, "show",
                               old_tip + ":state.json"))
        self.assertEqual(old["r1_guard"]["operations"]["operation-00001"]["status"],
                         "recorded")
        self.assertEqual(len(old["r1_guard"]["operations"]), 1)

    def test_receipt_id_cannot_be_replayed_under_new_cycle(self):
        op = self.op()
        self.tx("reserve", value=op)
        self.tx("record", value=op + "=" + self.receipt(op))
        self.tx("complete")
        self.tx("acquire", owner="second", generation=0)
        op2 = self.op(operation="operation-00002", effect="external-effect-00002")
        self.tx("reserve", owner="second", generation=2, value=op2)
        unchanged = self.tip()
        with self.assertRaisesRegex(r.Blocked, "receipt ID replay"):
            self.tx("record", owner="second", generation=2,
                    value=op2 + "=" + self.receipt(op2))
        self.assertEqual(self.tip(), unchanged)
        self.assertEqual(self.tx("inspect")["pending"], op2)

    def test_cross_cycle_source_cycle_agent_operation_and_effect_tampering(self):
        op = self.op()
        self.tx("reserve", value=op)
        baseline = self.tip()
        forged = [
            {"cycle_id": "wrong-cycle-00001"},
            {"agent": "wrong-agent"},
            {"operation_id": "other-operation-001"},
            {"effect_id": "other-effect-00001"},
            {"source": "f" * 40},
            {"receipt_id": "x"},
            {"proof": ""},
        ]
        for override in forged:
            with self.subTest(override=override):
                with self.assertRaises(r.Blocked):
                    self.tx("record", value=op + "=" + self.receipt(op, **override))
                self.assertEqual(self.tip(), baseline)
        self.tx("record", value=op + "=" + self.receipt(op))
        self.assertIsNone(self.tx("inspect")["pending"])

    def test_lost_external_outcome_stays_pending_across_expiry(self):
        op = self.op()
        self.tx("reserve", value=op)
        before = self.tip()
        with patch.object(r.time, "time", return_value=10**10):
            with self.assertRaisesRegex(r.Blocked, "unresolved external operation"):
                self.tx("acquire", owner="retry", generation=0)
            with self.assertRaisesRegex(r.Blocked, "inactive lease"):
                self.tx("record", value=op + "=" + self.receipt(op))
        self.assertEqual(self.tip(), before)
        self.assertEqual(self.tx("inspect")["r1_guard"]["operations"][
            "operation-00001"]["status"], "reserved")

    def test_concurrent_reserve_has_one_cas_winner(self):
        op = self.op()
        def contender(i):
            try:
                return self.tx("reserve", value=op)["pending"] == op
            except (r.Blocked, subprocess.CalledProcessError):
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            accepted = list(pool.map(contender, range(6)))
        self.assertEqual(sum(accepted), 1)
        state = self.tx("inspect")
        self.assertEqual(len(state["r1_guard"]["operations"]), 1)
        self.assertEqual(len(state["r1_guard"]["effects"]), 1)
        self.assertEqual(state["pending"], op)

    def test_concurrent_completion_has_one_cas_winner(self):
        op = self.op()
        self.tx("reserve", value=op)
        body = op + "=" + self.receipt(op)
        def contender(i):
            try:
                return self.tx("record", value=body)["pending"] is None
            except (r.Blocked, subprocess.CalledProcessError):
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            accepted = list(pool.map(contender, range(6)))
        self.assertEqual(sum(accepted), 1)
        state = self.tx("inspect")
        self.assertEqual(state["r1_guard"]["operations"]["operation-00001"]["status"],
                         "recorded")
        self.assertEqual(state["r1_guard"]["receipts"],
                         {"external-receipt-00001": "operation-00001"})
        self.assertEqual(state["generation"], 1)


    def test_unsigned_or_tampered_external_receipt_does_not_complete(self):
        op = self.op()
        self.tx("reserve", value=op)
        good = json.loads(self.receipt(op))
        mutations = [
            {**good, "attestation": None},
            {**good, "proof": "forged external evidence"},
            {**good, "receipt_id": "forged-receipt-00002"},
            {**good, "attestation": {**good["attestation"],
                                    "signature": "f" * 64}},
            {**good, "attestation": {**good["attestation"],
                                    "key_id": "rogue-verifier"}},
        ]
        for bad in mutations:
            before = self.tip()
            with self.assertRaises(r.Blocked):
                self.tx("record", value=op + "=" + json.dumps(bad, sort_keys=True))
            self.assertEqual(self.tip(), before)
            self.assertEqual(self.tx("inspect")["pending"], op)
        self.tx("record", value=op + "=" + json.dumps(good, sort_keys=True))
        self.assertIsNone(self.tx("inspect")["pending"])

    def test_missing_trusted_verifier_key_blocks_even_well_formed_signature(self):
        op = self.op()
        self.tx("reserve", value=op)
        signed = self.receipt(op)
        before = self.tip()
        with patch.dict(os.environ, {"OFC_R2_VERIFIER_KEY": ""}):
            with self.assertRaisesRegex(r.Blocked, "trusted verifier key missing"):
                self.tx("record", value=op + "=" + signed)
        self.assertEqual(self.tip(), before)
        self.assertEqual(self.tx("inspect")["pending"], op)

    def test_independent_agent_domain_rejects_cross_agent_signature(self):
        op = self.op()
        self.tx("reserve", value=op)
        good = json.loads(self.receipt(op))
        before = self.tip()
        with patch.object(r, "AGENT", "not-" + r.AGENT):
            with self.assertRaises(r.Blocked):
                self.tx("record", value=op + "=" + json.dumps(good, sort_keys=True))
        self.assertEqual(self.tip(), before)

    def test_no_success_by_legacy_merge_record_or_callback_recovery(self):
        intent = json.dumps({"repository": "fixture/repo", "pr": 17})
        with self.assertRaises(r.Blocked):
            self.tx("record", value=intent + "=forged")
        op = self.op()
        self.tx("reserve", value=op)
        before = self.tip()
        with self.assertRaisesRegex(r.Blocked, "arbitrary verifier"):
            r.recover_verified(self.remote, owner="bypass", source=self.source,
                               operation=op, evidence=self.receipt(op),
                               verifier=lambda *_: True)
        self.assertEqual(self.tip(), before)

    def test_legacy_string_reservation_cannot_bypass_r1_guard(self):
        op = self.op()
        self.tx("reserve", value=op)
        self.tx("record", value=op + "=" + self.receipt(op))
        before = self.tip()
        with self.assertRaisesRegex(r.Blocked, "legacy external reservation forbidden"):
            self.tx("reserve", value="legacy-qwen-public-trial")
        self.assertEqual(self.tip(), before)
        self.assertIsNone(self.tx("inspect")["pending"])

    def test_independent_repository_has_independent_global_keys(self):
        sibling = str(pathlib.Path(self.remote).parent / "sibling.git")
        r.git("init", "--quiet", "--bare", sibling)
        r.git("push", sibling, self.source + ":refs/heads/main")
        independent = r.transact(sibling, "acquire", "worker", 0, self.source)
        first_op = self.op()
        self.tx("reserve", value=first_op)
        sibling_op = json.dumps({
            "protocol": r.R1_PROTOCOL, "agent": r.AGENT,
            "cycle_id": independent["cycle"],
            "operation_id": "operation-00001",
            "effect_id": "external-effect-00001",
            "source": self.source}, sort_keys=True)
        result = r.transact(sibling, "reserve", "worker", 1, self.source, sibling_op)
        self.assertEqual(result["pending"], sibling_op)
        self.assertNotEqual(result["cycle"], self.first["cycle"])

    def test_verified_merge_effect_and_receipt_tombstones_reject_cross_cycle_replay(self):
        state = {"schema": 1, "agent": r.AGENT, "cycle": "cycle-merge-1",
                 "source": self.source, "results": {}, "phase": "open"}
        repo = r.REMOTE.removeprefix("https://github.com/").removesuffix(".git")
        intent = {"repository": repo, "pr": 77,
                  "operation_id": "merge-receipt-00077", "head_sha": "b"*40,
                  "base_sha": self.source}
        receipt = dict(intent, merge_commit_sha="c"*40)
        r.r1_note_verified_merge(state, json.dumps(intent), json.dumps(receipt))
        before = copy.deepcopy(state)
        with self.assertRaisesRegex(r.Blocked, "already executed"):
            r.r1_note_verified_merge(state, json.dumps(intent), json.dumps(receipt))
        other = dict(intent, operation_id="merge-receipt-00078")
        with self.assertRaisesRegex(r.Blocked, "already executed"):
            r.r1_note_verified_merge(state, json.dumps(other), json.dumps(
                dict(other, merge_commit_sha="d"*40)))
        self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
