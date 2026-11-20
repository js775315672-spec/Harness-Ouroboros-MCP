"""Fail-closed projections from one ORIL dataset manifest into split/raw validators.

This is an offline adapter, not a model-training or promotion gate.
The canonical manifest must be independently pinned before projections are trusted.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

SPLITS = ("train", "validation", "test")
FIELDS = {"sample_id", "content_sha256", "group_id", "source_id", "relative_path"}
HEX = re.compile(r"[0-9a-f]{64}\Z")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _bad_constant(value):
    raise ValueError("nonfinite JSON value: " + value)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=_unique_pairs, parse_constant=_bad_constant)


def project(manifest):
    """Reject missing/extra fields rather than silently discarding evidence."""
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "splits"}:
        raise ValueError("canonical manifest keys invalid")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("unsupported schema_version")
    splits = manifest["splits"]
    if not isinstance(splits, dict) or set(splits) != set(SPLITS):
        raise ValueError("all three splits required")
    for split in SPLITS:
        if not isinstance(splits[split], list) or not splits[split]:
            raise ValueError("nonempty split required: " + split)
        for item in splits[split]:
            if not isinstance(item, dict) or set(item) != FIELDS:
                raise ValueError("sample must have exactly five canonical fields")
            if not isinstance(item["content_sha256"], str) or not HEX.fullmatch(item["content_sha256"]):
                raise ValueError("invalid content digest")
            for key in FIELDS - {"content_sha256"}:
                val = item[key]
                if not isinstance(val, str) or not val or val.strip() != val:
                    raise ValueError("invalid " + key)
    split_view = {"schema_version": 1, "splits": {
        split: [{k: item[k] for k in ("sample_id", "content_sha256", "group_id", "source_id")}
                for item in splits[split]] for split in SPLITS}}
    raw_view = {"schema_version": 1, "splits": {
        split: [{k: item[k] for k in ("sample_id", "relative_path", "content_sha256")}
                for item in splits[split]] for split in SPLITS}}
    return split_view, raw_view


def run(manifest, expected_sha256, root, fingerprint, split_audit, raw_verify):
    """Use the original independent validators; never infer their success."""
    split_view, raw_view = project(manifest)
    pinned = fingerprint(manifest, expected_sha256)
    if not pinned["pin_matches"]:
        return {"status": "fail", "failed_stage": "manifest_pin", "manifest_pin": pinned,
                "training_approved": False, "promotion_approved": False}
    split = split_audit(split_view)
    if split["split_integrity"] != "pass":
        return {"status": "fail", "failed_stage": "split_integrity",
                "manifest_pin": pinned, "split_audit": split,
                "training_approved": False, "promotion_approved": False}
    raw = raw_verify(raw_view, root)
    ok = raw["raw_sample_integrity"] == "pass"
    return {"status": "pass" if ok else "fail",
            "failed_stage": None if ok else "raw_sample_integrity",
            "manifest_pin": pinned, "split_audit": split, "raw_audit": raw,
            "dataset_provenance": "unverified",
            "semantic_leakage": "unmeasured",
            "independent_model_evaluation": "unmeasured",
            "training_approved": False, "promotion_approved": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    # No implicit imports from unreviewed dependencies. CI tests pinned revisions.
    from scripts.oril_v2_dataset_manifest_attestation import fingerprint
    from scripts.oril_v2_dataset_split_audit import audit
    from scripts.oril_v2_raw_sample_integrity import verify
    result = run(load(args.manifest), args.expected_sha256, args.root, fingerprint, audit, verify)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
