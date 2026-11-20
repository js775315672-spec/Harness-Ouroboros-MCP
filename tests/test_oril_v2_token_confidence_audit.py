import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_token_confidence_audit import token_confidence_audit
D = "a"*64
A = "b"*64
B = "c"*64

def rows(n=40, *, model=A, tokens=100):
    return [dict(task_id=f"task-{i}",group_id=f"group-{i}",
                 dataset_sha256=D,model_sha256=model,seed=7,
                 correct=True,input_tokens=tokens,output_tokens=0,
                 latency_ms=100) for i in range(n)]

class TokenConfidenceTests(unittest.TestCase):
    def test_uniform_savings_pass_both_gates(self):
        result=token_confidence_audit(rows(),rows(model=B,tokens=70))
        self.assertTrue(result["token_saving_point_estimate_pass"])
        self.assertTrue(result["token_saving_pass"])
        self.assertEqual(result["status"],"향상")
        self.assertEqual(result["token_bootstrap_95ci"],[30,30])

    def test_outlier_savings_do_not_pass_lower_confidence(self):
        a=rows()
        b=rows(model=B)
        a[0]["input_tokens"]=2000
        b[0]["input_tokens"]=0
        report=token_confidence_audit(a,b)
        self.assertTrue(report["token_saving_point_estimate_pass"])
        self.assertFalse(report["token_saving_pass"])
        self.assertLess(report["token_bootstrap_95ci"][0],20)
        self.assertNotEqual(report["status"],"향상")

    def test_single_correlated_group_not_independent(self):
        a=rows()
        b=rows(model=B,tokens=60)
        for x,y in zip(a,b):
            x["group_id"]=y["group_id"]="Family"
        report=token_confidence_audit(a,b)
        self.assertEqual(report["independent_groups_proxy"],1)
        self.assertFalse(report["token_saving_pass"])
        self.assertEqual(report["status"],"판단불가")

    def test_alias_groups_still_one_group(self):
        a=rows()
        b=rows(model=B,tokens=60)
        for i,(x,y) in enumerate(zip(a,b)):
            x["group_id"]=y["group_id"]=["Ａ","A"," a ","ａ"][i%4]
        self.assertEqual(token_confidence_audit(a,b)["independent_groups_proxy"],1)

    def test_quality_regression_blocks_claim_even_with_tokens(self):
        a=rows()
        b=rows(model=B,tokens=50)
        for x in b[:20]:
            x["correct"]=False
        report=token_confidence_audit(a,b)
        self.assertTrue(report["token_saving_pass"])
        self.assertFalse(report["quality_noninferiority_pass"])
        self.assertNotEqual(report["status"],"향상")

    def test_zero_baseline_denominator_rejected(self):
        with self.assertRaisesRegex(ValueError,"nonzero"):
            token_confidence_audit(rows(tokens=0),rows(model=B,tokens=0))

    def test_zero_denominator_bootstrap_does_not_pass(self):
        a=rows()
        b=rows(model=B,tokens=0)
        for i in range(39):
            a[i]["input_tokens"]=0
        report=token_confidence_audit(a,b)
        self.assertIsNone(report["token_bootstrap_95ci"])
        self.assertFalse(report["token_saving_pass"])
        self.assertGreater(report["token_bootstrap_zero_baseline_resamples"],0)

    def test_unmatched_task_sets_fail(self):
        b=rows(model=B)
        b[0]["task_id"]="changed"
        with self.assertRaisesRegex(ValueError,"paired"):
            token_confidence_audit(rows(),b)

    def test_invalid_bootstrap_samples_fail(self):
        with self.assertRaisesRegex(ValueError,"bootstrap"):
            token_confidence_audit(rows(),rows(model=B),samples=99)

    def test_no_attestation_claim(self):
        report=token_confidence_audit(rows(),rows(model=B,tokens=70))
        self.assertFalse(report["independent_evaluation_attested"])
        self.assertFalse(report["gpu_training_attested"])
        self.assertFalse(report["model_quality_gain_attested"])

    def test_repeatable_bootstrap(self):
        a,b=rows(),rows(model=B,tokens=70)
        self.assertEqual(token_confidence_audit(a,b),token_confidence_audit(a,b))

    def test_cli_outputs_uncertainty_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)/"a.jsonl"
            cand=Path(tmp)/"b.jsonl"
            out=Path(tmp)/"report.json"
            for p,items in ((base,rows()),(cand,rows(model=B,tokens=70))):
                p.write_text("".join(json.dumps(x)+"\n" for x in items))
            r=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/"scripts"/"oril_v2_token_confidence_audit.py"),
                              "--baseline",str(base),"--candidate",str(cand),"--output",str(out)],
                             capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertTrue(json.loads(out.read_text())["token_saving_pass"])

if __name__=="__main__":
    unittest.main()
