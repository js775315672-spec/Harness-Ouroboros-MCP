import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from oril_v2_cpu_pair_report_audit import verify


def valid():
    return {
        "schema_version":1,
        "experiment":"synthetic_random_weight_qwen2_cpu_paired_inference",
        "n_pairs":2,"n_real_generations":4,"config_sha256":"a"*64,
        "compact_input_tokens":[5,6],"verbose_input_tokens":[10,12],
        "input_token_reduction_pct_median":50.0,
        "compact_elapsed_seconds_median":1.2,"verbose_elapsed_seconds_median":1.3,
        "paired_verbose_minus_compact_seconds_median":0.1,
        "paired_elapsed_differences_seconds":[0.1,0.1],
        "pair_orders":["compact_first","verbose_first"],"pair_order_observed":True,
        "pretrained_weights":False,"gpu_used":False,"optimizer_steps":0,
        "lora_adapter_created":False,"independent_heldout_evaluation":False,
        "model_intelligence_gain":None,"independent_quality_n":0,
        "training_cost":None,"inference_cost":None,
        "performance_gain_verified":False,"warning":"Synthetic random weights only.",
    }


class AuditTests(unittest.TestCase):
    def test_valid_synthetic_report_not_model_gain(self):
        x=verify(valid())
        self.assertTrue(x["token_median_arithmetic_verified"])
        self.assertFalse(x["individual_latency_medians_independently_verified"])
        self.assertFalse(x["model_quality_verified"])
        self.assertFalse(x["provenance_attested"])

    def test_token_savings_cannot_be_inflated(self):
        r=valid();r["input_token_reduction_pct_median"]=99
        with self.assertRaisesRegex(ValueError,"token saving"):verify(r)

    def test_paired_latency_cannot_be_inflated(self):
        r=valid();r["paired_verbose_minus_compact_seconds_median"]=9
        with self.assertRaisesRegex(ValueError,"paired latency"):verify(r)

    def test_generation_count_mismatch(self):
        r=valid();r["n_real_generations"]=6
        with self.assertRaisesRegex(ValueError,"generation count"):verify(r)

    def test_fabricated_order_rejected(self):
        r=valid();r["pair_order_observed"]=False
        with self.assertRaisesRegex(ValueError,"unobserved"):verify(r)

    def test_unbalanced_order_rejected(self):
        r=valid();r["pair_orders"]=["compact_first"]*2
        with self.assertRaisesRegex(ValueError,"unbalanced"):verify(r)

    def test_missing_order_is_allowed_but_not_certified(self):
        r=valid();r["pair_orders"]=None;r["pair_order_observed"]=False
        self.assertFalse(verify(r)["provenance_attested"])

    def test_fake_training_claim_rejected(self):
        for field,value in (("gpu_used",True),("lora_adapter_created",True),
                            ("pretrained_weights",True),("optimizer_steps",1),
                            ("independent_quality_n",5),("model_intelligence_gain",0.3),
                            ("performance_gain_verified",True),("training_cost",0)):
            with self.subTest(field=field):
                r=valid();r[field]=value
                with self.assertRaisesRegex(ValueError,"unsupported"):verify(r)

    def test_nonfinite_latency_rejected(self):
        r=valid();r["paired_elapsed_differences_seconds"]=[float("nan"),0.1]
        with self.assertRaisesRegex(ValueError,"vector values"):verify(r)

    def test_boolean_token_count_rejected(self):
        r=valid();r["compact_input_tokens"]=[True,6]
        with self.assertRaisesRegex(ValueError,"vector values"):verify(r)

    def test_extra_field_rejected(self):
        r=valid();r["training_complete"]=True
        with self.assertRaisesRegex(ValueError,"schema"):verify(r)

    def test_digest_must_be_sha256(self):
        r=valid();r["config_sha256"]="fake"
        with self.assertRaisesRegex(ValueError,"digest"):verify(r)

    def test_duplicate_json_key_rejected_by_cli(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/"report.json"
            s=json.dumps(valid())
            p.write_text(s[:-1]+',"gpu_used":true}')
            run=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/
                "scripts"/"oril_v2_cpu_pair_report_audit.py"),str(p)],capture_output=True,text=True)
            self.assertNotEqual(run.returncode,0)
            self.assertIn("duplicate JSON key",run.stderr)

    def test_real_summary_function_roundtrip(self):
        from oril_v2_tiny_qwen_cpu_paired_benchmark import summarize
        sample=[{"compact":{"input_tokens":5,"output_tokens":3,"elapsed_seconds":1.2},
                 "verbose":{"input_tokens":10,"output_tokens":3,"elapsed_seconds":1.3}},
                {"compact":{"input_tokens":6,"output_tokens":3,"elapsed_seconds":1.4},
                 "verbose":{"input_tokens":12,"output_tokens":3,"elapsed_seconds":1.5}}]
        report=summarize(sample,"a"*64,observed_orders=["compact_first","verbose_first"])
        self.assertTrue(verify(report)["schema_valid"])


if __name__=="__main__":
    unittest.main()
