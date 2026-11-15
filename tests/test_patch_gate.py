import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from patch_gate import inspect_patch
def proposal(path="scripts/example.py"):
    return {"provider":"qwen","status":"proposal","summary":"Fix code","patch":f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-old\n+new\n"}
class PatchGateTests(unittest.TestCase):
    def test_safe_patch_is_not_applied(self):
        result=inspect_patch(proposal())
        self.assertEqual(result["files"],["scripts/example.py"])
        self.assertFalse(result["patch_approved_for_application"])
    def test_workflow_modification_denied(self):
        with self.assertRaises(ValueError):inspect_patch(proposal(".github/workflows/harness.yml"))
    def test_parent_traversal_denied(self):
        with self.assertRaises(ValueError):inspect_patch(proposal("scripts/../secrets.txt"))
    def test_absolute_target_denied(self):
        with self.assertRaises(ValueError):inspect_patch(proposal("/etc/passwd"))
    def test_git_internal_denied(self):
        with self.assertRaises(ValueError):inspect_patch(proposal("scripts/.git/config"))
    def test_rename_denied(self):
        p=proposal();p["patch"]+="rename from scripts/example.py\n"
        with self.assertRaises(ValueError):inspect_patch(p)
    def test_mismatched_paths_denied(self):
        p=proposal();p["patch"]=p["patch"].replace("b/scripts/example.py","b/tests/example.py",1)
        with self.assertRaises(ValueError):inspect_patch(p)
    def test_empty_diff_denied(self):
        p=proposal();p["patch"]="diff --git "
        with self.assertRaises(ValueError):inspect_patch(p)
if __name__=="__main__":unittest.main()
