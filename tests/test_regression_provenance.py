import hashlib
import json
import pathlib
import tempfile
import unittest

from scripts.cloud_real_repo_proposal import _target_line
from scripts.disposable_regression_compare import verify_inference_provenance
from scripts.replacement_proposal import build_single_line_diff

ROOT=pathlib.Path(__file__).resolve().parents[1]
TARGET="tests/test_model_feedback_loop.py"

def evidence_files(directory):
    source=(ROOT/TARGET).read_bytes()
    n,old=_target_line(source.decode("utf-8"))
    new=old.replace(chr(92)*2+"n",chr(92)+"n")
    raw=new
    patch=build_single_line_diff(raw,old,n)
    raw=new.strip()
    candidate={"provider":"qwen","status":"proposal",
               "summary":"Scoped string-only test fix","patch":patch}
    candidate_path=directory/"candidate.json"
    candidate_bytes=(json.dumps(candidate,sort_keys=True,indent=2)+"\n").encode()
    candidate_path.write_bytes(candidate_bytes)
    report={"status":"accepted_for_review","model":"Qwen/Qwen2.5-0.5B-Instruct",
            "patch_origin":"deterministic_single_line_builder",
            "model_output_format":"single_python_assignment_line",
            "real_model_calls":1,
            "patch_applied":False,"merge_authorized":False,
            "full_harness_passed":False,
            "source_sha256":hashlib.sha256(source).hexdigest(),
            "candidate_sha256":hashlib.sha256(candidate_bytes).hexdigest(),
            "attempts":[{"attempt":1,"status":"accepted_for_review",
                         "response_preview":raw,
                         "response_chars":len(raw),
                         "response_sha256":hashlib.sha256(raw.encode()).hexdigest(),
                         "response_preview":raw,
                         "response_chars":len(raw),
                         "response_sha256":hashlib.sha256(raw.encode()).hexdigest(),
                         "synthesized_patch_sha256":
                         hashlib.sha256(patch.encode()).hexdigest()}]}
    report_path=directory/"inference.json"
    report_path.write_text(json.dumps(report),encoding="utf-8")
    return report_path,candidate_path,report

class RegressionProvenanceTests(unittest.TestCase):
    def test_valid_real_model_artifact_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,b,_=evidence_files(pathlib.Path(tmp))
            result=verify_inference_provenance(a,b,ROOT)
            self.assertTrue(result["provenance_verified"])
            self.assertEqual(result["real_model_calls"],1)
            self.assertEqual(len(result["candidate_sha256"]),64)

    def test_rejects_spoofed_source_or_candidate_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,b,report=evidence_files(pathlib.Path(tmp))
            for field in ("source_sha256","candidate_sha256"):
                with self.subTest(field=field):
                    tampered=dict(report,**{field:"0"*64})
                    a.write_text(json.dumps(tampered),encoding="utf-8")
                    with self.assertRaises(ValueError):
                        verify_inference_provenance(a,b,ROOT)

    def test_rejects_claimed_inference_without_calls_or_accepted_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,b,report=evidence_files(pathlib.Path(tmp))
            for change in ({"real_model_calls":0},
                           {"real_model_calls":True},
                           {"attempts":[]},
                           {"status":"rejected"},
                           {"patch_applied":True}):
                with self.subTest(change=change):
                    a.write_text(json.dumps(dict(report,**change)),encoding="utf-8")
                    with self.assertRaises(ValueError):
                        verify_inference_provenance(a,b,ROOT)

    def test_rejects_patch_substitution_even_with_updated_candidate_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,b,report=evidence_files(pathlib.Path(tmp))
            candidate=json.loads(b.read_text(encoding="utf-8"))
            candidate["patch"]=candidate["patch"].replace("+        answer=","+        answer =")
            payload=(json.dumps(candidate,sort_keys=True,indent=2)+"\n").encode()
            b.write_bytes(payload)
            report["candidate_sha256"]=hashlib.sha256(payload).hexdigest()
            a.write_text(json.dumps(report),encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_inference_provenance(a,b,ROOT)
