"""W06 safety tests use model stubs: they do not claim actual inference."""
import hashlib,pathlib,sys,unittest
from pathlib import Path
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
        prompt = w06.w02.build(ROOT)["prompt"]
        fn.assert_called_once_with(Path("binary"),Path("weights"),prompt,"7b")
        self.assertTrue(prompt.startswith("<|im_start|>system\n"))
        self.assertIn("Return one complete replacement Python function", prompt)
        self.assertEqual(r["prompt_sha256"], hashlib.sha256(prompt.encode("utf-8")).hexdigest())
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

    def test_exact_chatml_uses_the_bound_prompt_without_a_second_template(self):
        p3g=w06.p3g
        binary,weights=Path("binary"),Path("weights")
        prompt=w06.w02.build(ROOT)["prompt"]
        with patch.object(p3g,"verify_paths",return_value=(ROOT,binary,weights)), \
             patch.object(p3g.subprocess,"run",return_value=Mock(returncode=0,stdout="raw")) as run, \
             patch.object(p3g,"extract_completion",return_value=("answer",None)):
            raw,_=p3g.infer_prepared(binary,weights,prompt,"7b",**w06.INFERENCE_OPTIONS)
        self.assertEqual(raw,"answer")
        argv=run.call_args.args[0]
        self.assertEqual(argv[argv.index("--prompt")+1],prompt)
        self.assertIn("-no-cnv",argv)
        self.assertIn("--no-escape",argv)
        self.assertNotIn("--jinja",argv)
        self.assertEqual(argv[argv.index("--temp")+1],"0.35")
        self.assertEqual(argv[argv.index("--seed")+1],"1085")
        self.assertEqual(w06.inference_config_sha256(),w06.w04.digest_json(argv[5:]))
        self.assertIn("--jinja",p3g.inference_flags("7b"))

    def test_model_entry_uses_exact_chatml_and_rejects_replayed_candidate(self):
        raw="def validate(records):\n    return len(records)\n"
        original=w06.p3g.file_bytes(ROOT,w06.p3g.TARGET).decode("utf-8")
        candidate,_=w06.p3g.patch_original(original,raw)
        rejected=w06.sha(candidate.encode("utf-8"))
        with patch.object(w06.subprocess,"run",return_value=Mock(stdout="a"*40)), \
             patch.object(w06.p3g,"check_model"), \
             patch.object(w06.p3g,"infer_prepared",return_value=(raw,0.1)) as infer, \
             patch.object(w06,"REJECTED_CANDIDATE_DIGESTS",frozenset({rejected})):
            result=w06.execute(ROOT,"a"*40,123,Path("binary"),Path("weights"),Path("metadata"))
        infer.assert_called_once_with(Path("binary"),Path("weights"),w06.w02.build(ROOT)["prompt"],
                                      "7b",**w06.INFERENCE_OPTIONS)
        self.assertEqual(result["schema"],"p3l-w06-duplicate-rejected-v1")
        self.assertEqual(result["raw_response"],raw)
        self.assertEqual(result["candidate_source_sha256"],rejected)
        self.assertEqual(result["model_calls"],1)

    def test_review_sha_or_run_id_missing_fails_before_model(self):
        for sha,run_id in (("x"*40,123),("a"*40,0)):
            with self.subTest(sha=sha,run_id=run_id):
                with self.assertRaises(ValueError):
                    w06.execute(ROOT,sha,run_id,Path("x"),Path("y"),Path("z"),infer_fn=Mock())
if __name__=="__main__":
    unittest.main()
