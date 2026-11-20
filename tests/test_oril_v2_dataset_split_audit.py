"""Fail-closed data split audit regression tests (synthetic, no training)."""
import copy
import unittest

from scripts.oril_v2_dataset_split_audit import audit


def sample(i, group=None, digest=None):
    return {"sample_id": i, "group_id": group or i, "source_id": "synthetic",
            "content_sha256": digest or format(int(i[-1], 16) + 1, "064x")}


def fixture():
    return {"schema_version": 1, "splits": {
        "train": [sample("a1"), sample("a2", group="a1")],
        "validation": [sample("b3")],
        "test": [sample("c4")]}}
    

class SplitAuditTests(unittest.TestCase):
    def test_clean_splits_pass_without_claiming_training(self):
        out = audit(fixture())
        self.assertEqual(out["split_integrity"], "pass")
        self.assertEqual(out["counts"], {"train": 2, "validation": 1, "test": 1})
        self.assertEqual(out["model_training"], "unverified")
        self.assertFalse(out["promotion_approved"])

    def test_same_content_across_train_and_test_fails(self):
        data = fixture()
        data["splits"]["test"][0]["content_sha256"] = data["splits"]["train"][0]["content_sha256"]
        self.assertEqual(audit(data)["split_integrity"], "fail")
        self.assertEqual(len(audit(data)["overlaps"]["content_sha256"]), 1)

    def test_same_group_across_train_and_validation_fails(self):
        data = fixture()
        data["splits"]["validation"][0]["group_id"] = "a1"
        self.assertEqual(audit(data)["split_integrity"], "fail")
        self.assertEqual(len(audit(data)["overlaps"]["group_id"]), 1)

    def test_same_id_across_splits_fails(self):
        data = fixture()
        data["splits"]["test"][0]["sample_id"] = "a1"
        self.assertEqual(audit(data)["split_integrity"], "fail")

    def test_duplicate_id_within_train_fails(self):
        data = fixture()
        data["splits"]["train"].append(copy.deepcopy(data["splits"]["train"][0]))
        self.assertEqual(audit(data)["split_integrity"], "fail")

    def test_same_group_within_train_allowed(self):
        self.assertEqual(audit(fixture())["split_integrity"], "pass")

    def test_missing_test_split_rejected(self):
        data = fixture()
        del data["splits"]["test"]
        with self.assertRaises(ValueError):
            audit(data)

    def test_empty_validation_rejected(self):
        data = fixture()
        data["splits"]["validation"] = []
        with self.assertRaises(ValueError):
            audit(data)

    def test_invalid_digest_rejected(self):
        data = fixture()
        data["splits"]["test"][0]["content_sha256"] = "not-a-hash"
        with self.assertRaises(ValueError):
            audit(data)

    def test_uppercase_digest_rejected(self):
        data = fixture()
        data["splits"]["test"][0]["content_sha256"] = "A" * 64
        with self.assertRaises(ValueError):
            audit(data)

    def test_missing_provenance_rejected(self):
        data = fixture()
        del data["splits"]["train"][0]["source_id"]
        with self.assertRaises(ValueError):
            audit(data)

    def test_boolean_version_rejected(self):
        data = fixture()
        data["schema_version"] = True
        with self.assertRaises(ValueError):
            audit(data)

    def test_extra_top_level_fields_rejected(self):
        data = fixture()
        data["training_approved"] = True
        with self.assertRaises(ValueError):
            audit(data)

    def test_invalid_source_rejected(self):
        data = fixture()
        data["splits"]["test"][0]["source_id"] = " "
        with self.assertRaises(ValueError):
            audit(data)


if __name__ == "__main__":
    unittest.main()
