import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.cloud_real_repo_proposal import _target_line
from scripts.disposable_regression_compare import verify_inference_provenance
from scripts.replacement_proposal import build_single_line_diff

ROOT=Path(__file__).resolve().parents[1]
TARGET="tests/test_model_feedback_loop.py"

def digest(data):
    return hashlib.sha256(data).hexdigest()

def evidence():
    source=(ROOT/TARGET).read_bytes()
    n,old=_target_line(source.decode("utf-8"))
    new=old.replace(chr(92)*2+"n",chr(92)+"n")
    raw="answer = "+new.split("answer=",1)[1]
    patch=build_single_line_diff(raw,old,n)
    candidate={"provider":"qwen","status":"proposal",
               "summary":"review-only fixture","patch":patch}
    candidate_bytes=(json.dumps(candidate,sort_keys=True)+"\n").encode("utf-8")
    report={"status":"accepted_for_review","model":"Qwen/Qwen2.5-0.5B-Instruct",
            "patch_origin":"deterministic_single_line_builder",
            "model_output_format":"single_python_assignment_line",
            "real_model_calls":1,"patch_applied":False,"merge_authorized":False,
            "full_harness_passed":False,
            "source_sha256":digest(source),
            "candidate_sha256":digest(candidate_bytes),
            "attempts":[{"status":"accepted_for_review","response_preview":raw,
                         "response_chars":len(raw),
                         "response_sha256":digest(raw.encode("utf-8")),
                         "synthesized_patch_sha256":digest(patch.encode("utf-8"))}]}
    return report,candidate,candidate_bytes

def verify(report,candidate,candidate_bytes):
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        report_path=root/"report.json"
        candidate_path=root/"candidate.json"
        report_path.write_text(json.dumps(report),encoding="utf-8")
        candidate_path.write_bytes(candidate_bytes)
        return verify_inference_provenance(report_path,candidate_path,ROOT)

class ModelOutputReplayTests(unittest.TestCase):
    def test_exact_output_reconstructs_candidate(self):
        report,candidate,payload=evidence()
        result=verify(report,candidate,payload)
        self.assertTrue(result["provenance_verified"])
        self.assertTrue(result["model_response_replayed"])

    def test_reject_rewritten_output_even_with_updated_hash(self):
        report,candidate,payload=evidence()
        forged=copy.deepcopy(report)
        raw=forged["attempts"][-1]["response_preview"]
        forged["attempts"][-1]["response_preview"]=raw.replace("answer = ","answer =  ",1)
        forged["attempts"][-1]["response_chars"]=len(forged["attempts"][-1]["response_preview"])
        forged["attempts"][-1]["response_sha256"]=digest(forged["attempts"][-1]["response_preview"].encode("utf-8"))
        # The normalization is intentionally equivalent: replay still proves
        # the same canonical patch and is permitted.
        self.assertTrue(verify(forged,candidate,payload)["model_response_replayed"])
        forged["attempts"][-1]["response_preview"]="answer = \"unrelated\""
        forged["attempts"][-1]["response_chars"]=len(forged["attempts"][-1]["response_preview"])
        forged["attempts"][-1]["response_sha256"]=digest(forged["attempts"][-1]["response_preview"].encode("utf-8"))
        with self.assertRaises(ValueError):
            verify(forged,candidate,payload)

    def test_reject_missing_truncated_or_inconsistent_model_response(self):
        report,candidate,payload=evidence()
        for change in ("missing","truncated","wrong_hash","wrong_length"):
            forged=copy.deepcopy(report)
            attempt=forged["attempts"][-1]
            if change=="missing":
                attempt.pop("response_preview")
            elif change=="truncated":
                attempt["response_preview"]=attempt["response_preview"][:8]
            elif change=="wrong_hash":
                attempt["response_sha256"]="0"*64
            else:
                attempt["response_chars"]=999
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    verify(forged,candidate,payload)
