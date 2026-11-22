"""Fail-closed, offline evaluation of a Qwen candidate receipt (no model invocation)."""
import hashlib
import json
import re
from pathlib import Path

ROLE = "ouroboros"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")


class EvidenceError(ValueError):
    pass


def verify_receipt(receipt, *, expected_role=ROLE):
    """Only verifies a candidate's declared evidence shape; not independent quality."""
    if not isinstance(receipt, dict) or receipt.get("role") != expected_role:
        raise EvidenceError("independent role mismatch")
    for field in ("model_id", "model_revision", "input_sha256", "prompt_sha256",
                  "weights_sha256", "output_sha256", "evaluator_sha", "candidate_sha"):
        value = receipt.get(field)
        if not isinstance(value, str) or not value:
            raise EvidenceError("missing " + field)
    for field in ("input_sha256", "prompt_sha256", "weights_sha256", "output_sha256"):
        if not HEX64.fullmatch(receipt[field]):
            raise EvidenceError("invalid digest: " + field)
    for field in ("evaluator_sha", "candidate_sha"):
        if not HEX40.fullmatch(receipt[field]):
            raise EvidenceError("invalid commit: " + field)
    run = receipt.get("run_id")
    if type(run) is not int or run <= 0:
        raise EvidenceError("missing real Actions run ID")
    if receipt.get("independent_pass") is True and not receipt.get("independent_evaluation_receipt"):
        raise EvidenceError("independent PASS requires separately verified receipt")
    return True


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify_output(receipt, output_path):
    verify_receipt(receipt)
    if digest(Path(output_path).read_bytes()) != receipt["output_sha256"]:
        raise EvidenceError("output bytes differ from declared digest")
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt")
    parser.add_argument("output")
    args = parser.parse_args()
    verify_output(json.loads(Path(args.receipt).read_text(encoding="utf-8")), args.output)
    print(json.dumps({"role": ROLE, "receipt_valid": True, "quality_improved": None}))


if __name__ == "__main__":
    main()
