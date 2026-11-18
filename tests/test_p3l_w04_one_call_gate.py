"""W04 one-shot safety preflight with strict provenance and retry bounds."""
import pathlib,sys,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import p3l_w04_one_call_gate as w04

class W04OneCallGateTests(unittest.TestCase):
    def test_one_call_only_after_w01_w03_verified(self):
        r=w04.plan()
        self.assertEqual(r["decision"],"allow_one_model_call")
        self.assertEqual(r["w03_rule_checks"],19)
        self.assertEqual(r["max_attempts"],1)
        self.assertEqual(r["model_calls"],0)
        self.assertFalse(r["model_invoked"])
        self.assertFalse(r["merge_authorized"])
        self.assertTrue(r["model_config_only_not_weights"])

    def test_any_history_exhausts_single_attempt_budget(self):
        with self.assertRaises(ValueError):
            w04.plan(history=[{}])

    def test_w02_w03_sha_mismatch_is_rejected(self):
        bad=w04.w03.diagnose()
        bad["w02_prompt_sha256"]="0"*64
        with patch.object(w04.w03,"diagnose",return_value=bad):
            with self.assertRaisesRegex(ValueError,"handoff invalid"):
                w04.plan()

    def test_wrong_model_is_forbidden(self):
        with self.assertRaises(ValueError):
            w04.plan(model_id="unknown")

    def test_deterministic_bound_task(self):
        a=w04.plan()
        b=w04.plan()
        self.assertEqual(a,b)
        self.assertEqual(len(a["task_sha256"]),64)
        self.assertEqual(len(a["model_config_sha256"]),64)

if __name__=="__main__":
    unittest.main()
