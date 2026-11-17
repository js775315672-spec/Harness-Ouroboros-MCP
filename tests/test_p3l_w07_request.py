"""Safety-only tests: no model calls and no actual promotion."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from p3l_w07_request import BRIDGE, SPEC, build_request, canonical, digest, save_request


class W07RequestTests(unittest.TestCase):
    SHA = "1" * 40

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for file in (SPEC, BRIDGE):
            target = self.root / file
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("safe test stub\n", encoding="utf-8")

    def test_deterministic_sha_bound_request(self):
        a = build_request(self.root, self.SHA)
        b = build_request(self.root, self.SHA)
        self.assertEqual(a, b)
        proof = dict(a)
        self.assertEqual(proof.pop("request_sha256"), digest(canonical(proof)))
        self.assertEqual(a["review_commit"], self.SHA)

    def test_blocks_invalid_sha(self):
        for bad in ("f" * 39, "A" * 40, "0" * 41, "not-sha", "../foo"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                build_request(self.root, bad)

    def test_missing_or_symlink_input(self):
        (self.root / SPEC).unlink()
        with self.assertRaises(ValueError):
            build_request(self.root, self.SHA)
        (self.root / SPEC).symlink_to(self.root / BRIDGE)
        with self.assertRaises(ValueError):
            build_request(self.root, self.SHA)

    def test_altered_input_changes_binding(self):
        first = build_request(self.root, self.SHA)
        (self.root / SPEC).write_text("another spec", encoding="utf-8")
        second = build_request(self.root, self.SHA)
        self.assertNotEqual(first["spec_sha256"], second["spec_sha256"])
        self.assertNotEqual(first["request_sha256"], second["request_sha256"])

    def test_no_model_or_promotion_claims(self):
        req = build_request(self.root, self.SHA)
        self.assertEqual(req["model_calls"], 0)
        self.assertFalse(req["executor_connected"])
        self.assertFalse(req["candidate_verified"])
        self.assertFalse(req["promotion_eligible"])
        self.assertFalse(req["promotion_authorized"])
        self.assertFalse(req["merge_authorized"])
        self.assertFalse(req["active_executor_modified"])
        self.assertEqual(req["prerequisites"]["W05_independent_replay"], "NOT_ATTESTED")

    def test_rejects_unsafe_artifact_paths(self):
        req = build_request(self.root, self.SHA)
        for bad in ("/tmp/evil.json", "../evil.json", "artifacts/p3l-w08/request.json",
                    "artifacts/p3l-w07/../../evil.json"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                save_request(self.root, bad, req)

    def test_save_is_idempotent_but_not_overwriting(self):
        req = build_request(self.root, self.SHA)
        path = "artifacts/p3l-w07/request.json"
        save_request(self.root, path, req)
        save_request(self.root, path, req)
        altered = copy.deepcopy(req)
        altered["status"] = "PROMOTED"
        with self.assertRaises(ValueError):
            save_request(self.root, path, altered)

    def test_output_symlink_block(self):
        req = build_request(self.root, self.SHA)
        (self.root / "artifacts").symlink_to(self.root / "scripts", target_is_directory=True)
        with self.assertRaises(ValueError):
            save_request(self.root, "artifacts/p3l-w07/request.json", req)


if __name__ == "__main__":
    unittest.main()
