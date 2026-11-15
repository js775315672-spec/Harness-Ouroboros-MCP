import pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from isolated_patch_stage import stage_patch
def proposal():
    return {"provider":"qwen","status":"proposal","summary":"Fix fixture","patch":"diff --git a/tests/sample.txt b/tests/sample.txt\n--- a/tests/sample.txt\n+++ b/tests/sample.txt\n@@ -1 +1 @@\n-before\n+after\n"}
class IsolatedPatchStageTests(unittest.TestCase):
    def test_stage_without_source_modification(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);(root/"tests").mkdir();f=root/"tests/sample.txt";f.write_text("before\n")
            result=stage_patch(proposal(),root)
            self.assertEqual(result["status"],"staged_in_disposable_copy")
            self.assertEqual(f.read_text(),"before\n")
            self.assertFalse(result["model_code_executed"])
            self.assertFalse(result["harness_passed"])
    def test_invalid_patch_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);(root/"tests").mkdir()
            with self.assertRaises(ValueError):stage_patch(proposal(),root)
    def test_workflow_target_denied(self):
        with tempfile.TemporaryDirectory() as d:
            p=proposal();p["patch"]=p["patch"].replace("tests/sample.txt",".github/workflows/harness.yml")
            with self.assertRaises(ValueError):stage_patch(p,d)
if __name__=="__main__":unittest.main()
