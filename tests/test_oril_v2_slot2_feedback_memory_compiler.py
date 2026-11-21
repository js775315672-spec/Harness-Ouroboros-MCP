import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_slot2_feedback_memory_compiler import compile_memory, load_jsonl

def row(i="c1", **kwargs):
    d = {
        "cycle_id": i, "candidate_sha": "a"*40, "baseline_sha": "b"*40,
        "evaluator_sha": "c"*40, "heldout_digest": "d"*64,
        "evidence_sha256": "e"*64,
        "evidence_url": "https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/123",
        "independent_review": True, "heldout": True,
        "model_weights_changed": False, "gpu_training_proven": False,
        "adapter_sha256": None, "metric": "accuracy",
        "baseline_value": 0.7, "candidate_value": 0.8,
        "direction": "higher", "outcome": "pass",
        "hypothesis": "Compact examples may improve accuracy.",
        "experiment": "Run 30 frozen heldout groups with independent review.",
    }
    d.update(kwargs)
    return d

class MemoryTests(unittest.TestCase):
    def test_pass_still_never_promotes(self):
        x = compile_memory([row()])[0]
        self.assertEqual(x["verdict"], "verified_candidate")
        self.assertFalse(x["promotion_allowed"])
        self.assertFalse(x["review_provenance_attested"])

    def test_self_report_cannot_pass(self):
        self.assertEqual(compile_memory([row(independent_review=False)])[0]["verdict"], "no_verified_improvement")

    def test_public_only_cannot_pass(self):
        self.assertEqual(compile_memory([row(heldout=False)])[0]["verdict"], "no_verified_improvement")

    def test_inconclusive_cannot_pass(self):
        self.assertEqual(compile_memory([row(outcome="inconclusive")])[0]["verdict"], "no_verified_improvement")

    def test_failed_cannot_pass(self):
        self.assertEqual(compile_memory([row(outcome="fail")])[0]["verdict"], "no_verified_improvement")

    def test_worse_candidate_cannot_pass(self):
        self.assertEqual(compile_memory([row(candidate_value=0.6)])[0]["verdict"], "no_verified_improvement")

    def test_equal_candidate_cannot_pass(self):
        self.assertEqual(compile_memory([row(candidate_value=0.7)])[0]["verdict"], "no_verified_improvement")

    def test_lower_is_better(self):
        self.assertEqual(compile_memory([row(metric="tokens", direction="lower", candidate_value=0.6)])[0]["verdict"], "verified_candidate")

    def test_no_fake_lora(self):
        with self.assertRaisesRegex(ValueError, "GPU and adapter"):
            compile_memory([row(model_weights_changed=True)])

    def test_no_fake_gpu(self):
        with self.assertRaisesRegex(ValueError, "adapter SHA"):
            compile_memory([row(gpu_training_proven=True)])

    def test_gpu_claim_still_not_auto_proven(self):
        r = compile_memory([row(model_weights_changed=True, gpu_training_proven=True, adapter_sha256="f"*64)])[0]
        self.assertFalse(r["model_weight_gain_proven"])

    def test_no_hidden_answers_in_output(self):
        r = compile_memory([row()])[0]
        self.assertNotIn("heldout_digest", r)
        self.assertNotIn("baseline_value", r)

    def test_duplicate_cycle_fails(self):
        with self.assertRaisesRegex(ValueError, "duplicate cycle"):
            compile_memory([row(), row()])

    def test_missing_field_fails(self):
        x = row()
        del x["evaluator_sha"]
        with self.assertRaisesRegex(ValueError, "schema"):
            compile_memory([x])

    def test_nan_fails(self):
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            compile_memory([row(candidate_value=float("nan"))])

    def test_invalid_url_fails(self):
        with self.assertRaisesRegex(ValueError, "evidence_url"):
            compile_memory([row(evidence_url="https://example.com")])

    def test_deterministic_order(self):
        a = [row("z"), row("a")]
        self.assertEqual(compile_memory(a), compile_memory(list(reversed(a))))

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)/"in.jsonl"
            p.write_text(json.dumps(row())[:-1] + ',"cycle_id":"different"}\n')
            with self.assertRaisesRegex(ValueError, "duplicate JSON"):
                load_jsonl(p)

    def test_cli_output(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)/"in.jsonl"
            out = Path(t)/"out.jsonl"
            p.write_text(json.dumps(row())+"\n")
            script = Path(__file__).resolve().parents[1]/"scripts"/"oril_v2_slot2_feedback_memory_compiler.py"
            run = subprocess.run([sys.executable,str(script),"--input",str(p),"--output",str(out)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(json.loads(out.read_text().strip())["promotion_allowed"],False)

    def test_input_output_collision(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)/"in.jsonl"
            p.write_text(json.dumps(row())+"\n")
            script = Path(__file__).resolve().parents[1]/"scripts"/"oril_v2_slot2_feedback_memory_compiler.py"
            run = subprocess.run([sys.executable,str(script),"--input",str(p),"--output",str(p)],capture_output=True,text=True)
            self.assertNotEqual(run.returncode,0)

if __name__ == "__main__":
    unittest.main()
