"""Qwen local model checkpoint path preflight: synthetic filesystem tests only."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_local_qwen_adapter import ensure_local_model


class CheckpointSymlinkTests(unittest.TestCase):
    def test_normal_nested_model_directory_is_allowed(self):
        with tempfile.TemporaryDirectory() as root:
            model = Path(root) / "parent" / "checkpoint"
            model.mkdir(parents=True)
            (model / "config.json").write_text("{}")
            self.assertEqual(ensure_local_model(str(model)), str(model.resolve()))

    def test_direct_model_directory_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            model = Path(root) / "real"
            model.mkdir()
            (model / "config.json").write_text("{}")
            link = Path(root) / "alias"
            link.symlink_to(model, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                ensure_local_model(str(link))

    def test_symlinked_parent_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            parent = Path(root) / "real"
            model = parent / "model"
            model.mkdir(parents=True)
            (model / "config.json").write_text("{}")
            alias = Path(root) / "alias"
            alias.symlink_to(parent, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                ensure_local_model(str(alias / "model"))

    def test_symlinked_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            model = Path(root) / "model"
            model.mkdir()
            config = Path(root) / "config.json"
            config.write_text("{}")
            (model / "config.json").symlink_to(config)
            with self.assertRaisesRegex(ValueError, "config.json must not be a symlink"):
                ensure_local_model(str(model))

    def test_missing_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "config.json missing"):
                ensure_local_model(root)

    def test_missing_model_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "existing non-symlink"):
                ensure_local_model(str(Path(root) / "missing"))

    def test_dotdot_does_not_bypass_symlinked_parent(self):
        with tempfile.TemporaryDirectory() as root:
            parent = Path(root) / "real"
            model = parent / "model"
            model.mkdir(parents=True)
            (model / "config.json").write_text("{}")
            alias = Path(root) / "alias"
            alias.symlink_to(parent, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                ensure_local_model(str(alias / "model" / ".." / "model"))


if __name__ == "__main__":
    unittest.main()
