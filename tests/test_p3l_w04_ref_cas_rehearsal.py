"""Check reference identity and fail-closed handling of uncertain writes."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from p3l_w04_ref_cas_rehearsal import REF_PREFIX, REHEARSAL_BASE, claim

FIRST, SECOND = "1" * 40, "2" * 40


class RefClaimTests(unittest.TestCase):
    def test_separate_head_claims_share_one_immutable_ref(self):
        records = {}

        def request(method, path, data=None):
            if method == "POST":
                args = json.loads(data)
                ref, sha = args["ref"], args["sha"]
                if ref in records:
                    return 422, b'{}'
                records[ref] = sha
                status = 201
            else:
                ref = path.replace("/ref/", "refs/", 1)
                status = 200
            return status, json.dumps({"ref": ref, "object": {"type": "commit", "sha": records[ref]}})

        first = claim(REHEARSAL_BASE, FIRST, request)
        second = claim(REHEARSAL_BASE, SECOND, request)
        replay = claim(REHEARSAL_BASE, FIRST, request)
        self.assertTrue(first["ref"].startswith(REF_PREFIX))
        self.assertEqual(first["outcome"], "START_RECORDED")
        self.assertEqual(second["outcome"], "DUPLICATE_BLOCKED")
        self.assertEqual(replay["outcome"], "DUPLICATE_BLOCKED")
        self.assertEqual(records, {first["ref"]: FIRST})
        self.assertEqual(second["recorded_head"], FIRST)

    def test_lost_acknowledgement_does_not_retry_or_admit(self):
        request = Mock(side_effect=TimeoutError("response lost"))
        with self.assertRaises(TimeoutError):
            claim(REHEARSAL_BASE, FIRST, request)
        request.assert_called_once()

    def test_conflict_without_a_persisted_record_is_unverified(self):
        request = Mock(side_effect=[(422, b'{}'), (404, b'{}')])
        with self.assertRaisesRegex(ValueError, "no confirmed durable record"):
            claim(REHEARSAL_BASE, FIRST, request)
        self.assertEqual(request.call_count, 2)

    def test_unrelated_or_wrong_target_success_response_is_rejected(self):
        request = Mock(return_value=(201, '{"ref":"refs/heads/other","object":'
                                           '{"type":"commit","sha":"' + FIRST + '"}}'))
        with self.assertRaisesRegex(ValueError, "exact GitHub ref"):
            claim(REHEARSAL_BASE, FIRST, request)
        with self.assertRaisesRegex(ValueError, "unexpected review revisions"):
            claim(SECOND, FIRST, request)
        request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
