#!/usr/bin/env python3
"""Read-only, fail-closed contract for the eight-lane Ouroboros P1 preflight.

P1a deliberately does not run a model, accept patches, trust external CI or
publish branches. An attestation/commit belongs to a separate trusted verifier.
"""

import hashlib
import json
from pathlib import Path, PurePosixPath
import re


REPOSITORY = "js775315672-spec/Harness-Ouroboros-MCP"
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
ARCHITECTURE = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
LANES = tuple(f"{n:02d}" for n in range(1, 9))
ORACLES = (
    "python3 -m unittest discover -s tests -q",
    "python3 scripts/governance.py",
    "python3 scripts/harness_check.py",
)
PROTECTED = (
    ".github/workflows/",
    "harness-policy.json",
    "scripts/governance.py",
    "scripts/harness_check.py",
    "scripts/review_decision_gate.py",
    "production-secrets/",
)
ROOTS = ("scripts/", "tests/", "docs/")
EXPECTED_KEYS = {
    "schema", "repository", "target_scope", "goal", "execution_mode",
    "automatic_model_execution", "automatic_remote_push",
    "automatic_pr_creation", "automatic_merge", "human_approval_required",
    "paid_api_allowed", "user_provided_secrets_allowed", "scheduler_enabled",
    "epoch_minutes", "worker_budget_seconds", "checkpoint_interval_minutes",
    "max_parallel", "max_children_per_attested_parent",
    "max_pending_children_per_epoch", "max_epochs_without_renewed_approval",
    "frozen_oracle_commands", "protected_paths", "lanes",
}
LANE_KEYS = {
    "id", "architecture_key", "title", "high_level_goal", "hypothesis",
    "candidate_source_paths", "accept_only_if", "worktree_only",
}
REQUIRED_ACCEPTANCE = (
    "new committed source diff plus identical frozen Harness/regression/security "
    "suite plus independent exact-SHA CI attestation"
)


def _digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False,
                    separators=(",", ":")).encode("utf-8")).hexdigest()


def _strict(obj, key, value):
    if type(obj.get(key)) is not type(value) or obj[key] != value:
        raise ValueError(f"unsafe or unsupported {key}")


def _clean_root(path):
    if not isinstance(path, str) or path not in ROOTS:
        raise ValueError("candidate root is not approved")
    parts = PurePosixPath(path).parts
    if path.startswith("/") or ".." in parts or "\\" in path:
        raise ValueError("untrusted candidate path")
    return path


def validate_config(config):
    """Validate exact P0 read-only config. Never silently authorize P1 model runs."""
    if not isinstance(config, dict) or set(config) != EXPECTED_KEYS:
        raise ValueError("unexpected self-evolution config schema")
    expected = {
        "schema": 1, "repository": REPOSITORY,
        "target_scope": "self-repository-only",
        "execution_mode": "read-only-infrastructure-smoke",
        "automatic_model_execution": False,
        "automatic_remote_push": False,
        "automatic_pr_creation": False,
        "automatic_merge": False,
        "human_approval_required": True,
        "paid_api_allowed": False,
        "user_provided_secrets_allowed": False,
        "scheduler_enabled": False,
        "epoch_minutes": 60, "worker_budget_seconds": 3000,
        "checkpoint_interval_minutes": 5,
        "max_parallel": 8, "max_children_per_attested_parent": 8,
        "max_pending_children_per_epoch": 64,
        "max_epochs_without_renewed_approval": 1,
    }
    for key, value in expected.items():
        _strict(config, key, value)
    if (not isinstance(config["goal"], str) or
            len(config["goal"].strip()) < 24 or
            len(config["goal"].encode("utf-8")) > 1000):
        raise ValueError("unsafe shared goal")
    if (type(config["frozen_oracle_commands"]) is not list or
            tuple(config["frozen_oracle_commands"]) != ORACLES):
        raise ValueError("oracle list was changed")
    if (type(config["protected_paths"]) is not list or
            tuple(config["protected_paths"]) != PROTECTED):
        raise ValueError("protected-path list was changed")
    rows = config["lanes"]
    if type(rows) is not list or len(rows) != 8:
        raise ValueError("expected exactly eight lanes")
    if [row.get("id") if isinstance(row, dict) else None for row in rows] != list(LANES):
        raise ValueError("lane order or identity changed")
    architecture_keys = []
    for row in rows:
        if set(row) != LANE_KEYS:
            raise ValueError("unknown lane fields")
        if (not isinstance(row["architecture_key"], str) or
                not ARCHITECTURE.fullmatch(row["architecture_key"])):
            raise ValueError("invalid architecture")
        architecture_keys.append(row["architecture_key"])
        for key in ("title", "hypothesis"):
            if not isinstance(row[key], str) or not 3 <= len(row[key]) <= 500:
                raise ValueError("invalid lane description")
        if row["high_level_goal"] != config["goal"]:
            raise ValueError("lane goals diverged")
        if (type(row["candidate_source_paths"]) is not list or
                tuple(map(_clean_root, row["candidate_source_paths"])) != ROOTS):
            raise ValueError("lane source scope changed")
        if row["accept_only_if"] != REQUIRED_ACCEPTANCE:
            raise ValueError("acceptance gate was weakened")
        _strict(row, "worktree_only", True)
    if len(set(architecture_keys)) != 8:
        raise ValueError("duplicated architecture")
    return config


def load_config(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 131072:
        raise ValueError("missing/unsafe config file")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid JSON config") from exc
    return validate_config(config)


def build_manifests(config, base_sha):
    """Build exactly eight read-only inputs, with no possibility of success claims."""
    validate_config(config)
    if not isinstance(base_sha, str) or not COMMIT.fullmatch(base_sha):
        raise ValueError("source commit must be an exact 40-char lowercase SHA")
    shared = {
        "schema": 1,
        "repository": REPOSITORY,
        "base_sha": base_sha,
        "shared_goal_sha256": _digest(config["goal"]),
        "frozen_oracle_sha256": _digest(list(ORACLES)),
        "config_sha256": _digest(config),
        "candidate_source_roots": list(ROOTS),
        "policy": "read-only-preflight-no-model",
        "model_execution_authorized": False,
        "source_patch_generated": False,
        "candidate_verified": False,
        "ci_attested": False,
        "remote_push_authorized": False,
        "pr_creation_authorized": False,
        "merge_authorized": False,
        "human_review_required": True,
    }
    result = []
    for row in config["lanes"]:
        item = {**shared, "lane_id": row["id"],
                "architecture_key": row["architecture_key"],
                "architecture_hypothesis_sha256": _digest(row["hypothesis"])}
        item["contract_sha256"] = _digest(item)
        result.append(item)
    return result


def verify_manifests(config, base_sha, supplied):
    """Reject missing, duplicated, altered or invented claims in preflight records.

    A valid preflight is NOT evidence of code generation or model capability.
    """
    expected = build_manifests(config, base_sha)
    if type(supplied) is not list or len(supplied) != 8:
        raise ValueError("missing or extra task manifest")
    if supplied != expected:
        raise ValueError("preflight contracts differ from reviewed configuration")
    return {"status": "eight_read_only_preflights_validated", "lane_count": 8,
            "verified_model_patches": 0, "ci_attested_patches": 0,
            "remote_push_authorized": False, "merge_authorized": False}
