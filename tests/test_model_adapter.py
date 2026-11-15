import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from model_adapter import request,validate_response
class ModelAdapterTests(unittest.TestCase):
    def test_qwen_is_coder(self):
        result=request("qwen","Fix bug")
        self.assertEqual(result["role"],"coder")
        self.assertFalse(result["network_request_performed"])
    def test_gpt_oss_is_reviewer(self):
        self.assertEqual(request("gpt-oss","Review")["role"],"reviewer")
    def test_gemma_is_reviewer(self):
        self.assertEqual(request("gemma","Review")["role"],"reviewer")
    def test_unknown_provider_blocked(self):
        with self.assertRaises(ValueError):request("unknown","Fix bug")
    def test_bad_feedback_blocked(self):
        with self.assertRaises(ValueError):request("qwen","Fix bug",{"decision":"review"})
    def test_valid_patch_remains_untrusted(self):
        result=validate_response({"provider":"qwen","status":"proposal","summary":"Patch","patch":"diff --git a/x b/x\n"})
        self.assertFalse(result["patch_applied"])
        self.assertFalse(result["harness_passed"])
    def test_patch_without_diff_blocked(self):
        with self.assertRaises(ValueError):
            validate_response({"provider":"qwen","status":"proposal","summary":"Patch","patch":"rm -rf /"})
    def test_rejected_patch_blocked(self):
        with self.assertRaises(ValueError):
            validate_response({"provider":"gemma","status":"reject","summary":"unsafe","patch":"diff --git a/x b/x\n"})
if __name__=="__main__":unittest.main()
