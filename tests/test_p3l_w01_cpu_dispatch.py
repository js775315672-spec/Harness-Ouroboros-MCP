"""Negative controls for a non-executing W01 CPU handoff manifest."""
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from p3l_w01_request import build_request, save_request
from p3l_w01_cpu_dispatch import dispatch, load_request, REQUIRES

SOURCE = '''def validate(records):
    if not isinstance(records,list): raise ValueError("expected list")
    return len(records)
'''


def catalog(model):
    if model == "0.5b":
        return {"repo": "Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF", "filename": "qwen2.5-coder-0.5b-instruct-q4_k_m.gguf", "license": "apache-2.0"}
    if model == "14b":
        return {"repo": "Qwen/Qwen2.5-Coder-14B-Instruct-GGUF", "filename": "qwen2.5-coder-14b-instruct-q4_k_m.gguf", "license": "apache-2.0", "revision": "b" * 40, "sha256": "c" * 64}
    raise ValueError("unknown model")


class DispatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = pathlib.Path(temp.name).resolve()
        (self.root / "scripts").mkdir()
        (self.root / "docs/p3l").mkdir(parents=True)
        (self.root / "scripts/development_ledger.py").write_text(SOURCE, encoding="utf-8")
        (self.root / "docs/p3l/W01-ledger-contract.ko.md").write_text("W01 validated specification", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "scripts/development_ledger.py", "docs/p3l/W01-ledger-contract.ko.md"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.name=W01-test", "-c", "user.email=local@test.invalid", "commit", "-qm", "test fixture"], cwd=self.root, check=True)
        self.sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root, text=True).strip()
        self.req = pathlib.Path("artifacts/p3l-w01/request.json")
        save_request(self.root, self.req, build_request(self.root, self.sha))

    def make_dispatch(self, **kwargs):
        return dispatch(self.root, self.req, self.sha, model_catalog=catalog, **kwargs)

    def test_real_adapter_is_named_but_never_invoked(self):
        result = self.make_dispatch()
        self.assertEqual(result["adapter"], "gguf_cpu_runtime.CPUInference")
        self.assertFalse(result["execution_enabled"])
        self.assertEqual(result["actual_model_calls"], 0)
        self.assertFalse(result["candidate_verified"])
        self.assertFalse(result["merge_authorized"])
        self.assertEqual(result["required_approval_gates"], list(REQUIRES))
        self.assertFalse(result["model_pinned"])

    def test_repeat_is_deterministic(self):
        self.assertEqual(self.make_dispatch(), self.make_dispatch())

    def test_tampered_prompt_and_hash_are_blocked(self):
        target = self.root / self.req
        s = target.read_text(encoding="utf-8")
        target.write_text(s.replace("fixes=[]", "fixes=['']"), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.make_dispatch()

    def test_change_of_source_after_request_is_blocked(self):
        (self.root / "docs/p3l/W01-ledger-contract.ko.md").write_text("new contract", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.make_dispatch()

    def test_reject_unsupported_or_forged_model(self):
        with self.assertRaises(ValueError):
            self.make_dispatch(model_id="3b")
        with self.assertRaises(ValueError):
            dispatch_model_bad(self)

    def test_pinned_model_does_not_override_approval_gates(self):
        result = self.make_dispatch(model_id="14b")
        self.assertTrue(result["model_pinned"])
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["independent_replay_verified"])

    def test_reject_symlink_and_untrusted_path(self):
        src = self.root / self.req
        backup = self.root / "archive.json"
        backup.write_bytes(src.read_bytes())
        src.unlink()
        src.symlink_to(backup)
        with self.assertRaises(ValueError):
            load_request(self.root, self.req, self.sha)
        with self.assertRaises(ValueError):
            load_request(self.root, pathlib.Path("../../elsewhere"), self.sha)


def dispatch_model_bad(case):
    return dispatch(case.root, case.req, case.sha, model_id="0.5b",
                    model_catalog=lambda _: {"repo": "evil/model", "filename": "evil.gguf", "license": "apache-2.0"})


if __name__ == "__main__":
    unittest.main()
