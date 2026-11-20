"""Offline ORIL dataset split audit: never authorize training or promotion.

The caller supplies immutable, provenance-bound manifests. This module checks
identifiers and exact SHA-256 overlaps; it does not prove semantic independence,
correct labeling, model quality, or authenticity of the supplied manifests.
"""
import argparse
import json
import re
from pathlib import Path

HEX64 = re.compile(r"[0-9a-f]{64}\Z")
SPLITS = ("train", "validation", "test")


def _string(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def audit(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "splits"}:
        raise ValueError("manifest must contain only schema_version and splits")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("unsupported schema version")
    splits = manifest["splits"]
    if not isinstance(splits, dict) or set(splits) != set(SPLITS):
        raise ValueError("train, validation and test splits are all required")
    seen_ids, seen_hashes, seen_groups = {}, {}, {}
    overlaps = {"sample_id": [], "content_sha256": [], "group_id": []}
    counts = {}
    for split in SPLITS:
        samples = splits[split]
        if not isinstance(samples, list) or not samples:
            raise ValueError("each split must have nonempty sample list")
        counts[split] = len(samples)
        for sample in samples:
            if not isinstance(sample, dict) or set(sample) != {
                    "sample_id", "content_sha256", "group_id", "source_id"}:
                raise ValueError("sample requires exact provenance fields")
            for field in ("sample_id", "group_id", "source_id"):
                if not _string(sample[field]):
                    raise ValueError("invalid " + field)
            digest = sample["content_sha256"]
            if not isinstance(digest, str) or HEX64.fullmatch(digest) is None:
                raise ValueError("content_sha256 must be lowercase 64-hex")
            for field, seen in (("sample_id", seen_ids),
                                ("content_sha256", seen_hashes),
                                ("group_id", seen_groups)):
                key = sample[field]
                if key in seen and (field != "group_id" or seen[key] != split):
                    overlaps[field].append({"value": key, "first_split": seen[key],
                                            "second_split": split})
                else:
                    seen[key] = split
    return {
        "schema_version": 1,
        "counts": counts,
        "overlaps": overlaps,
        "split_integrity": "fail" if any(overlaps.values()) else "pass",
        "dataset_provenance": "unverified",
        "semantic_leakage": "unmeasured",
        "model_training": "unverified",
        "independent_model_evaluation": "unmeasured",
        "promotion_approved": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    result = audit(json.loads(args.manifest.read_text(encoding="utf-8")))
    print(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2))
    if result["split_integrity"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
