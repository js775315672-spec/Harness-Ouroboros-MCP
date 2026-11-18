"""W06 safety tests use model stubs: they do not claim actual inference."""
import hashlib,pathlib,sys,unittest
from unittest.mock import patch,Mock
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import p3l_w06_actual_model_once as w06

class W06AttemptTests(unittest.TestCase):
    def test_one_stub_call_creates_raw_sha_bound_source_receipt(self):
        fn=Mock(return_value=("def validate(records):\n    return len(records)\n",0.1))
        with patch.object(w06.subprocess,"run",return_value=Mock(stdout="a"*40)), \
             patch.object(w06.p3g,"check_model"):
            r=w06.execute(ROOT,"a"*40,123,Path("binary"),Path("weights"),Path("metadata"),infer_fn=fn)
        fn.assert_called_once()
        self.assertEqual(r["model_calls"],1)
        self.assertEqual(r["schema"],"p3l-w06-one-shot-output-v1")
        self.assertEqual(len(r["candidate_source_sha256"]),64)
        self.assertFalse(r["merge_authorized"])

    def test_static_failure_preserves_original_response_but_is_not_candidate(self):
        with patch.object(w06.subprocess,"run",return_value=Mock(stdout="a"*40)), \
             patch.object(w06.p3g,"check_model"):
            r=w06.execute(ROOT,"a"*40,123,Path("binary"),Path("weights"),Path("metadata"),infer_fn=lambda *x: ("import os\ndef validate(records):\n    return len(records)\n",0.1))
        self.assertEqual(r["schema"],"p3l-w06-static-rejected-v1")
        self.assertIsNone(r["candidate_source_sha256"])
        self.assertFalse(r["merge_authorized"])

    def test_review_sha_or_run_id_missing_fails_before_model(self):
        for sha,run_id in (("x"*40,123),("a"*40,0)):
            with self.subTest(sha=sha,run_id=run_id):
                with self.assertRaises(ValueError):
                    w06.execute(ROOT,sha,run_id,Path("x"),Path("y"),Path("z"),infer_fn=Mock())
if __name__=="__main__":
    unittest.main()
