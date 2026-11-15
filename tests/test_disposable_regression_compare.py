import pathlib
import tempfile
import unittest
from unittest import mock

from scripts.disposable_regression_compare import (
    prove_data_only_change, prepare_candidate, docker_regression)
from scripts.cloud_real_repo_proposal import _target_line
from scripts.replacement_proposal import build_single_line_diff

ROOT=pathlib.Path(__file__).resolve().parents[1]
TARGET="tests/test_model_feedback_loop.py"
MODULE="scripts/model_feedback_loop.py"

def replacement():
    original=(ROOT/TARGET).read_text(encoding="utf-8")
    number,old=_target_line(original)
    new=old.replace(chr(92)*2+"n",chr(92)+"n")
    lines=original.splitlines(keepends=True)
    lines[number-1]=new+"\n"
    updated="".join(lines)
    return original,updated,build_single_line_diff(new,old,number)

class DisposableRegressionCompareTests(unittest.TestCase):
    def test_only_test_string_literal_data_changes(self):
        original,updated,_=replacement()
        proof=prove_data_only_change(original,updated)
        self.assertTrue(proof["executable_ast_identical"])
        self.assertTrue(proof["only_string_literal_data_changed"])
        self.assertNotEqual(proof["old_literal_sha256"],proof["new_literal_sha256"])

    def test_reject_injected_executable_statement(self):
        original,updated,_=replacement()
        number,_=_target_line(original)
        lines=updated.splitlines(keepends=True)
        lines[number-1]=lines[number-1].rstrip("\n")+'; print("side effect")\n'
        with self.assertRaises(ValueError):
            prove_data_only_change(original,"".join(lines))

    def test_disposable_copy_can_apply_but_never_mutates_source(self):
        original,updated,patch=replacement()
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)/"repo"
            out=pathlib.Path(tmp)/"staging"
            for rel in (TARGET,MODULE):
                dest=root/rel
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes((ROOT/rel).read_bytes())
            staged=prepare_candidate(root,patch,out)
            self.assertTrue(staged["source_unchanged"])
            self.assertFalse(staged["model_code_executed"])
            self.assertTrue(staged["patch_applied_to_disposable_copy_only"])
            self.assertEqual((root/TARGET).read_text(encoding="utf-8"),original)
            self.assertEqual((out/"candidate"/TARGET).read_text(encoding="utf-8"),updated)
            self.assertEqual((out/"baseline"/TARGET).read_text(encoding="utf-8"),original)

    def test_patch_target_symlink_denied(self):
        _,_,patch=replacement()
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)/"repo"
            (root/"tests").mkdir(parents=True)
            (root/"scripts").mkdir()
            (root/TARGET).symlink_to(ROOT/TARGET)
            (root/MODULE).write_bytes((ROOT/MODULE).read_bytes())
            with self.assertRaises(ValueError):
                prepare_candidate(root,patch,pathlib.Path(tmp)/"work")

    def test_container_run_has_no_network_or_write_access(self):
        with tempfile.TemporaryDirectory() as temp:
            fake=mock.Mock(returncode=0,stdout="",
                           stderr="Ran 8 tests in 0.02s\n\nOK")
            with mock.patch("scripts.disposable_regression_compare.subprocess.run",return_value=fake) as run:
                result=docker_regression(temp)
            self.assertTrue(result["tests_passed"])
            command=run.call_args.args[0]
            for expected in ("--network=none","--read-only","--cap-drop=ALL",
                             "--security-opt=no-new-privileges","--pull=never",
                             "--user=65534:65534"):
                self.assertIn(expected,command)
            self.assertNotIn("GITHUB_TOKEN",str(command))
