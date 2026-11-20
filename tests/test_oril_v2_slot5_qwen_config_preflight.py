"""Synthetic checkpoint config preflight only; no real Qwen/GPU execution."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_local_qwen_adapter import ensure_local_model, run_inference


class QwenConfigPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config.json"

    def write(self, data):
        self.config.write_bytes(data)
        return str(self.root)

    def test_empty_object_is_accepted_for_existing_mock_contract(self):
        self.assertEqual(ensure_local_model(self.write(b"{}")), str(self.root.resolve()))

    def test_normal_metadata_is_accepted(self):
        self.assertEqual(ensure_local_model(self.write(b'{"model_type":"qwen2","hidden_size":64}')), str(self.root.resolve()))

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            ensure_local_model(self.write(b'{"model_type":"qwen2","model_type":"other"}'))

    def test_nonfinite_config_rejected(self):
        for value in (b"NaN", b"Infinity", b"-Infinity"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "nonfinite"):
                    ensure_local_model(self.write(b'{"hidden_size":' + value + b"}"))

    def test_invalid_json_rejected(self):
        for value in (b"{", b"not-json", b""):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "invalid"):
                    ensure_local_model(self.write(value))

    def test_invalid_utf8_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid"):
            ensure_local_model(self.write(b'{"key":"\xff"}'))

    def test_nonobject_config_rejected(self):
        for value in (b"[]", b"null", b'"str"', b"4"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "object"):
                    ensure_local_model(self.write(value))

    def test_exact_one_megabyte_bound(self):
        # Whitespace is valid JSON padding.
        value = b"{}" + b" " * (1048576 - 2)
        self.assertEqual(ensure_local_model(self.write(value)), str(self.root.resolve()))

    def test_oversize_rejected(self):
        value = b"{}" + b" " * (1048577 - 2)
        with self.assertRaisesRegex(ValueError, "1 MiB"):
            ensure_local_model(self.write(value))

    def test_malformed_config_fails_before_torch_import(self):
        request = {"question": "test", "case_id": "c", "seed": 0}
        self.write(b"{")
        with patch.dict(sys.modules, {"torch": None, "transformers": None}):
            with self.assertRaisesRegex(ValueError, "invalid"):
                run_inference(request, model_dir=str(self.root))


if __name__ == "__main__":
    unittest.main()
