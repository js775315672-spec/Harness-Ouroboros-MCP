"""Offline A/B protocol tests: parity, non-claims, safety, no model download."""
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from qwen_server_cli_comparison import (
    fixed_tasks, score_output, summarize, required_server_flags,
    bounded_process_path, run_server, compare_config, experiment, REPEATS, TASKS
)


class ServerVsCLITests(unittest.TestCase):
    def test_same_exact_four_prompts_and_two_fixed_tasks(self):
        tasks = fixed_tasks()
        self.assertEqual(len(tasks), REPEATS * len(TASKS))
        self.assertEqual(tasks[0], tasks[2])
        self.assertEqual(tasks[1], tasks[3])
        self.assertNotEqual(tasks[0], tasks[1])
        self.assertEqual([t[0] for t in tasks], [0, 1, 0, 1])

    def test_ast_gate_still_rejects_invalid_or_malicious_code(self):
        self.assertTrue(score_output("chr(13) in log", 13)["ast_accepted"])
        self.assertTrue(score_output("chr(127) in log", 127)["ast_accepted"])
        for raw in (
            "chr(127) in log", "True", "import os", "chr(13) in log or True",
            "__import__('os').system('id')", chr(27)+"[31m",
            "chr(13) in log\nprint(1)", ""
        ):
            with self.subTest(output=repr(raw)):
                self.assertFalse(score_output(raw, 13)["ast_accepted"])
        self.assertIsNone(score_output(None, 13)["response_sha256"])

    def test_common_renderer_marker_only_not_fake_acceptance(self):
        result = score_output("chr(13) in log [end of text]", 13)
        self.assertTrue(result["ast_accepted"])
        self.assertFalse(score_output("chr(13) in log[end of text]",13)["ast_accepted"])

    def test_speedup_only_if_exact_prompts_and_both_measured(self):
        def rows(engine, secs):
            return [{"task_id":TASKS[i%2][0], "prompt_sha256":str(i%2),
                     "ast_accepted":i%2==1,
                     "elapsed_seconds":s} for i,s in enumerate(secs)]
        cli={"call_results":rows("cli",[20,20,20,20]),
             "four_calls_wall_seconds":80,"peak_child_rss_kib":6000000}
        server={"call_results":rows("srv",[4,4,4,4]),
                "startup_seconds":22,"peak_server_rss_kib":5100000,
                "startup_plus_calls_wall_seconds":38}
        s=summarize(cli,server)
        self.assertTrue(s["equal_prompt_sequence"])
        self.assertEqual(s["median_request_latency_speedup_if_greater_than_one"],5.0)
        self.assertEqual(s["cli"]["ast_accepted"],2)
        self.assertEqual(s["server"]["ast_accepted"],2)
        self.assertFalse(s["autonomous_coding_proven"])
        server["call_results"][0]["prompt_sha256"]="wrong"
        self.assertFalse(summarize(cli,server)["equal_prompt_sequence"])
        self.assertIsNone(summarize(cli,server)["median_request_latency_speedup_if_greater_than_one"])

    def test_server_binary_help_verifies_required_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "llama-server"
            path.write_text("x")
            path.chmod(0o755)
            help_text="--model --host --port --ctx-size --threads --parallel"
            with patch("qwen_server_cli_comparison.subprocess.run",
                       return_value=SimpleNamespace(returncode=0,
                                                    stdout=help_text,stderr="")):
                result = required_server_flags(path)
            self.assertEqual(result["help_exit_code"],0)
            self.assertEqual(len(result["approved_cli_flags"]),6)
            with patch("qwen_server_cli_comparison.subprocess.run",
                       return_value=SimpleNamespace(returncode=0,
                                                    stdout="--model --port",stderr="")):
                with self.assertRaises(ValueError):
                    required_server_flags(path)

    def test_wrong_executable_or_symlink_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"llama-server"
            path.write_text("x")
            path.chmod(0o755)
            self.assertEqual(bounded_process_path(path,"llama-server"),path)
            with self.assertRaises(ValueError):
                bounded_process_path(path,"llama-completion")
            link=Path(tmp)/"link"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                bounded_process_path(link,"link")

    def test_opt_in_experiment_writes_evidence_not_model_code(self):
        cfg={"model":{"sha256":"f"*64,"revision":"d"*40}}
        def report(engine):
            return {"call_results":[{"task_id": TASKS[i%2][0],
                     "prompt_sha256":str(i%2), "ast_accepted":True,
                     "elapsed_seconds":4 if engine=="server" else 20}
                     for i in range(4)],
                    **({"four_calls_wall_seconds":80,
                       "peak_child_rss_kib":6_000_000} if engine=="cli" else
                       {"startup_seconds":12,"peak_server_rss_kib":5_000_000,
                        "startup_plus_calls_wall_seconds":28})}
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/"result"/"report.json"
            with (patch("qwen_server_cli_comparison.compare_config",
                        return_value=(cfg,"a"*64,Path("a"),Path("b"))),
                  patch("qwen_server_cli_comparison.required_server_flags",
                        return_value={"approved_cli_flags":["--host"]}),
                  patch("qwen_server_cli_comparison.run_cli",return_value=report("cli")),
                  patch("qwen_server_cli_comparison.run_server",return_value=report("server"))):
                result=experiment(ROOT,"a","b","c","d",output)
            self.assertEqual(result["status"],"comparison_measured")
            self.assertTrue(output.is_file())
            self.assertFalse(result["summary"]["merge_authorized"])
            self.assertEqual(json.loads(output.read_text())["seed"],42)
            with self.assertRaises(ValueError):
                experiment(ROOT,"a","b","c","d",output)

    def test_model_runs_never_contaminate_frozen_smoke_conditions(self):
        from frozen_qwen_benchmark_20 import read_config
        cfg,_ = read_config(ROOT)
        self.assertEqual(cfg["runtime"]["seed"],42)
        self.assertEqual(cfg["runtime"]["temperature"],0)
        self.assertEqual(cfg["model"]["quantization"],"Q4_K_M")
        self.assertTrue(cfg["gates"]["model_must_not_edit_tests"])


if __name__=="__main__":
    unittest.main()
