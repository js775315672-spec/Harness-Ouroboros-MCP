"""No-model tests of frozen 20-trial measurement semantics and provenance."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from frozen_qwen_benchmark_20 import (
    read_config, wilson, summarize, CaptureModel, TOTAL, prepare_model
)
from gguf_cpu_runtime import FROZEN_CPU_SEED


class FakeModel:
    def __init__(self):
        self.calls=0
    def generate(self,prompt):
        self.calls+=1
        return "chr(13) in log"


class FrozenMeasurementTests(unittest.TestCase):
    def test_manifest_is_pre_registered_and_restricted(self):
        config,sha=read_config(ROOT)
        self.assertEqual(config["repeats_required"],20)
        self.assertEqual(config["model"]["quantization"],"Q4_K_M")
        self.assertEqual(config["runtime"]["seed"],42)
        self.assertEqual(FROZEN_CPU_SEED,42)
        self.assertEqual(config["runtime"]["temperature"],0)
        self.assertTrue(config["gates"]["model_must_not_edit_tests"])
        self.assertTrue(config["gates"]["failures_count_in_denominator"])
        self.assertTrue(config["human_merge_required"])
        self.assertEqual(len(sha),64)

    def test_wilson_interval_handles_zero_and_twenty(self):
        self.assertEqual(wilson(0,0),[None,None])
        self.assertEqual(wilson(0,20)[0],0)
        self.assertEqual(wilson(20,20)[1],1)
        lo,hi=wilson(10,20)
        self.assertTrue(0<lo<.5<hi<1)

    def test_failures_and_budget_debit_full_denominator(self):
        base={"status":"model_failed","first_attempt_both":False}
        rows=[dict(base,trial=i) for i in range(1,21)]
        rows[0]["status"]="passed_in_runner"
        rows[0]["first_attempt_both"]=True
        rows[1]["status"]="infra_failed"
        rows[19]["status"]="not_started_budget"
        result=summarize(rows,"f"*64,"a"*40)
        self.assertEqual(result["planned_trials"],20)
        self.assertEqual(result["started_trials"],19)
        self.assertEqual(result["in_runner_two_task_passes"],1)
        self.assertEqual(result["in_runner_pass_rate_all_planned"],.05)
        self.assertEqual(result["infrastructure_failures"],1)
        self.assertEqual(result["not_started_due_to_budget"],1)
        self.assertFalse(result["measurement_complete"])
        self.assertFalse(result["general_autonomous_coding_proven"])
        self.assertIsNone(result["full_two_job_recovery_passes"])

    def test_duplicate_or_partial_trial_records_rejected(self):
        rows=[{"trial":1,"status":"passed_in_runner","first_attempt_both":True}]*20
        with self.assertRaises(ValueError):
            summarize(rows,"0"*64,"a"*40)
        with self.assertRaises(ValueError):
            summarize(rows[:19],"0"*64,"a"*40)

    def test_capture_keeps_original_response_and_prompt(self):
        capture=CaptureModel(FakeModel())
        response=capture.generate("benchmark prompt")
        self.assertEqual(response,"chr(13) in log")
        self.assertEqual(capture.raw_attempts[0]["response"],response)
        self.assertEqual(capture.raw_attempts[0]["prompt"],"benchmark prompt")
        self.assertEqual(len(capture.raw_attempts[0]["response_sha256"]),64)

    def test_manifest_does_not_accept_silent_gate_relaxation(self):
        config,_=read_config(ROOT)
        self.assertTrue(config["gates"]["ast_fixed_scope"])
        self.assertEqual(config["gates"]["regression_tests"],8)
        self.assertEqual(config["gates"]["negative_tests"],3)
        self.assertEqual(config["repeats_required"],TOTAL)


if __name__=="__main__":
    unittest.main()
