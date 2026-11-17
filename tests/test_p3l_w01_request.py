"""Local negative controls for an unexecuted, source-anchored W01 task."""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from p3l_w01_request import build_request, save_request

SHA = "a" * 40
SOURCE = '''import re

def validate(records):
    if not isinstance(records, list):
        raise ValueError("not a list")
    return len(records)
'''
SPEC = "W01 tests the contract, not model success."


class W01RequestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name).resolve()
        (self.root / "scripts").mkdir()
        (self.root / "docs/p3l").mkdir(parents=True)
        (self.root / "scripts/development_ledger.py").write_text(SOURCE, encoding="utf-8")
        (self.root / "docs/p3l/W01-ledger-contract.ko.md").write_text(SPEC, encoding="utf-8")

    def test_anchored_contract_not_execution(self):
        request = build_request(self.root, SHA)
        self.assertEqual(request["worker"], "W01")
        self.assertEqual(request["review_commit"], SHA)
        self.assertEqual(request["allowed_output"], ["docs/p3l/ledger-input-contract.ko.md"])
        self.assertEqual(request["model_calls"], 0)
        self.assertFalse(request["executor_connected"])
        self.assertFalse(request["candidate_verified"])
        self.assertFalse(request["merge_authorized"])
        self.assertIn("fixes=[]", request["prompt"])
        self.assertIn("def validate(records):", request["prompt"])
        self.assertNotIn("heldout_p3f_development_ledger", request["prompt"])

    def test_identical_input_is_deterministic(self):
        self.assertEqual(build_request(self.root, SHA), build_request(self.root, SHA))

    def test_changed_contract_changes_request(self):
        before = build_request(self.root, SHA)
        (self.root / "docs/p3l/W01-ledger-contract.ko.md").write_text(SPEC + " amended", encoding="utf-8")
        after = build_request(self.root, SHA)
        self.assertNotEqual(before["request_sha256"], after["request_sha256"])

    def test_reject_untrusted_commit_and_invalid_source(self):
        with self.assertRaises(ValueError):
            build_request(self.root, "bad")
        (self.root / "scripts/development_ledger.py").write_text("def unrelated(x): pass", encoding="utf-8")
        with self.assertRaises(ValueError):
            build_request(self.root, SHA)

    def test_reject_symlink_input(self):
        p = self.root / "scripts/development_ledger.py"
        alternate = self.root / "backup.py"
        alternate.write_text(SOURCE, encoding="utf-8")
        p.unlink()
        p.symlink_to(alternate)
        with self.assertRaises(ValueError):
            build_request(self.root, SHA)

    def test_save_idempotent_and_block_overwrite(self):
        request = build_request(self.root, SHA)
        out = pathlib.Path("artifacts/p3l-w01/request.json")
        save_request(self.root, out, request)
        save_request(self.root, out, request)
        changed = dict(request, status="ALTERED")
        with self.assertRaises(ValueError):
            save_request(self.root, out, changed)

    def test_reject_unsafe_output(self):
        request = build_request(self.root, SHA)
        for path in ("../request.json", "/tmp/request.json", "docs/task.json", "artifacts/../../escape"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                save_request(self.root, path, request)


if __name__ == "__main__":
    unittest.main()
