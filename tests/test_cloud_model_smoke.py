import ast,pathlib,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class CloudModelSmokeTests(unittest.TestCase):
    def test_script_import_does_not_download_weights(self):
        tree=ast.parse((ROOT/"scripts/cloud_model_smoke.py").read_text(encoding="utf-8"))
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call)]
        self.assertFalse(any(isinstance(c.func,ast.Attribute) and c.func.attr=="from_pretrained" and isinstance(getattr(c,"parent",None),ast.Module) for c in calls))
        self.assertIn("if __name__==\"__main__\"", (ROOT/"scripts/cloud_model_smoke.py").read_text(encoding="utf-8"))
    def test_default_model_small(self):
        text=(ROOT/"scripts/cloud_model_smoke.py").read_text(encoding="utf-8")
        self.assertIn("Qwen/Qwen2.5-0.5B-Instruct",text)
        self.assertIn("max_new_tokens=96",text)
        self.assertIn("patch_applied\":False",text)
    def test_real_call_evidence_distinguished_from_synthetic(self):
        text=(ROOT/"scripts/cloud_model_smoke.py").read_text(encoding="utf-8")
        self.assertIn('real_model_calls=real_model_calls[0]',text)
        self.assertIn('synthetic_responses=model_requests[0]-real_model_calls[0]',text)
        self.assertIn('final_response_sha256=hashlib.sha256',text)
        self.assertIn('repository_patch_proposed=False',text)
    def test_workflow_requires_manual_dispatch(self):
        text=(ROOT/".github/workflows/cloud-model-smoke.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:",text)
        self.assertNotIn("pull_request:",text)
        self.assertIn("contents: read",text)
        self.assertIn("timeout-minutes: 20",text)
if __name__=="__main__":unittest.main()
