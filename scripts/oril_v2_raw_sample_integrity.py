"""Offline raw-sample SHA-256 verifier for ORIL dataset manifests.

Independent of the manifest pin and split-overlap PRs. Reads only files under
a trusted local root; never trains, evaluates, or promotes a model.
"""
import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path, PurePosixPath

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SPLITS = ("train", "validation", "test")
CHUNK = 1024 * 1024


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("invalid JSON number: " + value)


def _safe_path(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative or "\x00" in relative:
        raise ValueError("invalid relative path")
    parts = PurePosixPath(relative).parts
    if (relative.startswith("/") or any(p in ("", ".", "..") for p in relative.split("/"))
            or parts[0].endswith(":")):
        raise ValueError("path traversal or absolute path")
    path = root
    for part in parts:
        path = path / part
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValueError("symlinks forbidden")
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("sample must be regular file")
    return path


def verify(manifest, root):
    """Fail closed on malformed manifest; report hash mismatch without approval."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("root must be an existing real directory")
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "splits"}:
        raise ValueError("invalid manifest structure")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("unsupported schema version")
    splits = manifest["splits"]
    if not isinstance(splits, dict) or set(splits) != set(SPLITS):
        raise ValueError("train, validation, test required")
    seen_ids = set()
    seen_paths = set()
    seen_inodes = set()
    mismatches = []
    checked = {s: 0 for s in SPLITS}
    for split in SPLITS:
        samples = splits[split]
        if not isinstance(samples, list) or not samples:
            raise ValueError("all splits require nonempty sample arrays")
        for item in samples:
            if not isinstance(item, dict) or set(item) != {"sample_id", "relative_path", "content_sha256"}:
                raise ValueError("sample requires sample_id, relative_path, content_sha256")
            sample_id = item["sample_id"]
            expected = item["content_sha256"]
            if not isinstance(sample_id, str) or not sample_id or sample_id.strip() != sample_id:
                raise ValueError("invalid sample_id")
            if not isinstance(expected, str) or not SHA256.fullmatch(expected):
                raise ValueError("invalid content_sha256")
            if sample_id in seen_ids:
                raise ValueError("duplicate sample_id")
            seen_ids.add(sample_id)
            rel = item["relative_path"]
            if rel in seen_paths:
                raise ValueError("duplicate relative_path")
            seen_paths.add(rel)
            path = _safe_path(root, rel)
            metadata = path.stat()
            inode = (metadata.st_dev, metadata.st_ino)
            if inode in seen_inodes:
                raise ValueError("hardlinked duplicate sample")
            seen_inodes.add(inode)
            digest = hashlib.sha256()
            # O_NOFOLLOW prevents replacing a final component with a symlink.
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            fd = os.open(path, flags)
            try:
                opened = os.fstat(fd)
                if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != inode:
                    raise ValueError("sample changed during open")
                with os.fdopen(fd, "rb", closefd=False) as handle:
                    while True:
                        block = handle.read(CHUNK)
                        if not block:
                            break
                        digest.update(block)
                after = os.fstat(fd)
                if (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (
                        opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns):
                    raise ValueError("sample changed during read")
            finally:
                os.close(fd)
            checked[split] += 1
            actual = digest.hexdigest()
            if actual != expected:
                mismatches.append({"split": split, "sample_id": sample_id,
                                   "expected_sha256": expected, "actual_sha256": actual})
    return {
        "schema_version": 1, "checked": checked,
        "total_checked": sum(checked.values()),
        "mismatches": mismatches,
        "raw_sample_integrity": "pass" if not mismatches else "fail",
        "manifest_authenticity": "unverified",
        "dataset_provenance": "unverified",
        "semantic_leakage": "unmeasured",
        "independent_model_evaluation": "unmeasured",
        "training_approved": False, "promotion_approved": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"),
                          object_pairs_hook=_reject_duplicate_keys,
                          parse_constant=_reject_constant)
    result = verify(manifest, args.root)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False))
    if result["raw_sample_integrity"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
