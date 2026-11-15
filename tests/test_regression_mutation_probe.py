import json
import pathlib
import tempfile
import unittest
from unittest import mock

from scripts.regression_mutation_probe import run_probe
from scripts.disposable_regression_compare import docker_mutation_probe
from scripts.cloud_real_repo_proposal import _target_line

ROOT=pathlib.Path(__file__).resolve().parents[1]
TARGET=ROOT/"tests/test_model_feedback_loop.py"


class RegressionMutationProbeTests(unittest.TestCase):
    def test_negative_control_distinguishes_baseline_from_fixed_fixture(self):
        original=TARGET.read_text(encoding="utf-8")
        number,old=_target_line(original)
        replacement=old.replace(chr(92)*2+"n",chr(92)+"n")
        self.assertNotEqual(old,replacement)
        lines=original.splitlines(keepends=True)
        lines[number-1]=replacement+"\n"
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp)
            baseline=root/"baseline.py"
            candidate=root/"candidate.py"
            baseline.write_text(original,encoding="utf-8")
            candidate.write_text("".join(lines),encoding="utf-8")
            before=run_probe(baseline)
            after=run_probe(candidate)
        self.assertEqual(before["target_tests_run"],1)
        self.assertEqual(after["target_tests_run"],1)
        self.assertFalse(before["mutant_detected"])
        self.assertTrue(after["mutant_detected"])
        self.assertFalse(before["model_generated_code_executed"])
        self.assertFalse(after["model_generated_code_executed"])

    def test_container_requires_locked_down_flags_and_parses_probe(self):
        payload={"mutant_detected":True,"target_tests_run":1,
                 "mutant_limited_to_trusted_probe":True,
                 "model_generated_code_executed":False}
        with tempfile.TemporaryDirectory() as temp:
            result=mock.Mock(returncode=0,stdout=json.dumps(payload),stderr="")
            with mock.patch("scripts.disposable_regression_compare.subprocess.run",
                            return_value=result) as execute:
                answer=docker_mutation_probe(temp)
        self.assertTrue(answer["mutant_detected"])
        self.assertTrue(answer["probe_in_isolated_container"])
        command=execute.call_args.args[0]
        for flag in ("--network=none","--read-only","--cap-drop=ALL",
                     "--security-opt=no-new-privileges","--user=65534:65534",
                     "--pull=never"):
            self.assertIn(flag,command)
        self.assertEqual(command[-3:],["-B","-m","scripts.regression_mutation_probe"])

    def test_rejects_fake_and_failed_probe_reports(self):
        with tempfile.TemporaryDirectory() as temp:
            for payload in ({"mutant_detected":"true","target_tests_run":1},
                            {"mutant_detected":True,"target_tests_run":0},
                            {"mutant_detected":True,"target_tests_run":1,
                             "mutant_limited_to_trusted_probe":True,
                             "model_generated_code_executed":True}):
                result=mock.Mock(returncode=0,stdout=json.dumps(payload),stderr="")
                with mock.patch("scripts.disposable_regression_compare.subprocess.run",
                                return_value=result):
                    with self.assertRaises(ValueError):
                        docker_mutation_probe(temp)
            failed=mock.Mock(returncode=2,stdout="",stderr="error")
            with mock.patch("scripts.disposable_regression_compare.subprocess.run",
                            return_value=failed):
                with self.assertRaises(ValueError):
                    docker_mutation_probe(temp)
