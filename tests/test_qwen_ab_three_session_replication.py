"""Offline evidence contract for three A/B sessions, including failures."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from qwen_ab_three_session_replication import session_summary, verify_batch, sha


def comparison():
    return {
        "comparison_kind":"identical_model_prompt_sampling_no_grammar_no_retry",
        "experimental_task_count":4, "merge_authorized":False,
        "summary":{
            "equal_prompt_sequence":True,"autonomous_coding_proven":False,
            "cli":{"attempts":4,"ast_accepted":2,"per_call_median_seconds":20},
            "server":{"attempts":4,"ast_accepted":2,"per_call_median_seconds":12},
            "server_startup_seconds":5.0,"cli_batch_wall_seconds":80,
            "server_startup_plus_batch_wall_seconds":53,
            "median_request_latency_speedup_if_greater_than_one":1.667,
        }
    }


class RestartReplicationTests(unittest.TestCase):
    def test_three_measured_sessions_preserve_all_observations(self):
        rows=[{"session":i,"status":"comparison_measured","report":comparison()}
              for i in (1,2,3)]
        result=session_summary(rows)
        self.assertEqual(result["sessions_measured"],3)
        self.assertEqual(result["sessions_failed"],0)
        self.assertEqual(result["median_session_ratio"],1.667)
        self.assertFalse(result["autonomous_coding_proven"])

    def test_failed_sessions_in_denominator(self):
        rows=[
            {"session":1,"status":"comparison_measured","report":comparison()},
            {"session":2,"status":"infrastructure_failed","report":None},
            {"session":3,"status":"infrastructure_failed","report":None},
        ]
        result=session_summary(rows)
        self.assertEqual(result["sessions_planned"],3)
        self.assertEqual(result["sessions_measured"],1)
        self.assertEqual(result["sessions_failed"],2)
        self.assertFalse(result["all_three_sessions_measured"])

    def test_missing_or_fake_attempts_never_count(self):
        rows=[{"session":i,"status":"comparison_measured","report":comparison()}
              for i in (1,2,3)]
        with self.assertRaises(ValueError):
            session_summary(rows[:2])
        rows[0]["report"]["summary"]["server"]["attempts"]=3
        with self.assertRaises(ValueError):
            session_summary(rows)

    def test_saved_files_must_match_report_and_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            rows=[]
            for i in (1,2,3):
                value=comparison()
                folder=root/("session_%02d"%i)
                folder.mkdir()
                payload=json.dumps(value,sort_keys=True).encode()
                (folder/"ab-report.json").write_bytes(payload)
                rows.append({"session":i,"status":"comparison_measured",
                             "report_sha256":sha(payload),"report":value,
                             "failure":None,"session_elapsed_seconds":1})
            result={"experiment":"qwen7b-ab-three-restarts-v1",
                    "protocol_version":1,"human_merge_required":True,
                    "sessions":rows,"summary":session_summary(rows)}
            (root/"replication-report.json").write_text(json.dumps(result))
            self.assertTrue(verify_batch(root)["all_three_sessions_measured"])
            (root/"session_01"/"ab-report.json").write_text("{}")
            with self.assertRaises(ValueError):
                verify_batch(root)

if __name__=="__main__":
    unittest.main()
