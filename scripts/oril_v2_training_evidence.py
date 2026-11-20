"""Offline, fail-closed ORIL v2 training evidence preflight.

This checks a *claim manifest*, not the truth of remote GitHub/GPU attestations.
It never authorizes training, evaluation, or promotion.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
STATES = ("PROPOSED", "AUTHORIZED", "TRAINING_STARTED",
          "TRAINING_COMPLETED_UNVERIFIED", "VERIFIED_TRAINING",
          "INDEPENDENTLY_EVALUATED", "APPROVED_FOR_PROMOTION", "PROMOTED")
REQUIRED = ("authorization_ref", "model_base_digest", "tokenizer_digest",
            "training_dataset_digest", "heldout_dataset_digest",
            "trainer_config_digest", "run_url", "gpu_telemetry_ref")


def validate(manifest, adapter_bytes=None, seen_run_ids=()):
    """Return (ok, errors); never treat a synthetic pass as real-world attestation."""
    errors = []
    if not isinstance(manifest, dict):
        return False, ["manifest_not_object"]
    if manifest.get("schema_version") != "oril-v2-training-evidence-0.1":
        errors.append("invalid_schema")
    status = manifest.get("status")
    if status not in STATES:
        errors.append("invalid_state")
        return False, errors
    if status in STATES[:4]:
        return False, errors + ["not_verified_training"]
    for key in REQUIRED:
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            errors.append("missing_" + key)
    for key in ("model_base_digest", "tokenizer_digest",
                "training_dataset_digest", "heldout_dataset_digest",
                "trainer_config_digest", "adapter_sha256"):
        if not SHA256.fullmatch(str(manifest.get(key, ""))):
            errors.append("invalid_" + key)
    if not SHA40.fullmatch(str(manifest.get("source_commit_sha", ""))):
        errors.append("invalid_source_commit_sha")
    if manifest.get("training_dataset_digest") == manifest.get("heldout_dataset_digest"):
        errors.append("train_heldout_digest_collision")
    steps = manifest.get("optimizer_steps")
    if type(steps) is not int or steps <= 0:
        errors.append("invalid_optimizer_steps")
    size = manifest.get("adapter_size_bytes")
    if type(size) is not int or size <= 0:
        errors.append("invalid_adapter_size")
    if adapter_bytes is None:
        errors.append("adapter_bytes_unavailable")
    elif not isinstance(adapter_bytes, bytes) or not adapter_bytes:
        errors.append("adapter_bytes_invalid")
    else:
        if len(adapter_bytes) != size:
            errors.append("adapter_size_mismatch")
        if hashlib.sha256(adapter_bytes).hexdigest() != manifest.get("adapter_sha256"):
            errors.append("adapter_digest_mismatch")
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        errors.append("missing_run_id")
    elif run_id in seen_run_ids:
        errors.append("duplicate_run_id")
    if not isinstance(manifest.get("gpu_device"), str) or not manifest["gpu_device"].strip():
        errors.append("missing_gpu_device")
    if manifest.get("trainer_exit_code") != 0 or type(manifest.get("trainer_exit_code")) is not int:
        errors.append("trainer_not_successful")
    if manifest.get("base_model_compatible") is not True:
        errors.append("base_adapter_incompatible")
    if manifest.get("heldout_contamination_free") is not True:
        errors.append("heldout_not_isolated")
    if status in STATES[5:] and not manifest.get("independent_eval_ref"):
        errors.append("missing_independent_eval")
    if status in STATES[6:] and not manifest.get("promotion_approval_ref"):
        errors.append("missing_promotion_approval")
    if status == "PROMOTED" and manifest.get("promotion_actor") == manifest.get("training_actor"):
        errors.append("self_promotion")
    return not errors, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--seen-run-ids", type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        adapter = args.adapter.read_bytes()
        seen = json.loads(args.seen_run_ids.read_text()) if args.seen_run_ids else []
        if not isinstance(seen, list) or any(not isinstance(x, str) for x in seen):
            raise ValueError("seen-run-ids must be a JSON array of strings")
        ok, errors = validate(manifest, adapter, seen)
    except (OSError, ValueError, UnicodeError) as exc:
        ok, errors = False, ["input_unavailable_or_invalid:" + type(exc).__name__]
    print(json.dumps({"preflight_pass": ok, "errors": errors,
                      "attestation_verified": False, "training_dispatched": False},
                     sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
