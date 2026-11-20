#!/usr/bin/env python3
"""Offline pinned-policy boundary for ORIL dataset ledgers.

A policy SHA256 pin MUST come from a separately controlled trusted channel.
Hashing the submitted policy and accepting its own digest does not give trust.
This is an experimental *input consistency* check, never a training approval.
"""
import argparse
import hashlib
import json
import pathlib
import re
import sys
import tempfile

try:
    from scripts.oril_v2_signed_ledger_boundary import verify
except ModuleNotFoundError:
    from oril_v2_signed_ledger_boundary import verify

HEX64 = re.compile(r"[0-9a-f]{64}\Z")
POLICY_FIELDS = {"schema_version", "dataset_id", "signer_id",
                 "min_version", "public_key_sha256", "checkpoint_sha256"}


def _parse_strict(blob):
    """Read one captured byte snapshot; reject JSON duplicate keys and NaNs."""
    def unique(pairs):
        result = {}
        for key, val in pairs:
            if key in result:
                raise ValueError("duplicate policy/checkpoint key")
            result[key] = val
        return result

    def invalid(_):
        raise ValueError("nonfinite JSON value")

    return json.loads(blob.decode("utf-8"), object_pairs_hook=unique,
                      parse_constant=invalid)


def _hash(blob):
    return hashlib.sha256(blob).hexdigest()


def verify_anchored(manifest, ledger, signature, public_key, checkpoint,
                    policy, trusted_policy_sha256, now=None):
    """Bind a *separately pinned* policy to the key and replay checkpoint."""
    output = {
        "anchor_consistent": False,
        "integrity_pass": False,
        "signature_valid": False,
        "replay_rejected": False,
        "provenance_verified": False,
        "training_approved": False,
        "promotion_approved": False,
    }
    try:
        if not isinstance(trusted_policy_sha256, str) or not HEX64.fullmatch(trusted_policy_sha256):
            raise ValueError("external trusted policy SHA256 pin required")
        policy_bytes = pathlib.Path(policy).read_bytes()
        if _hash(policy_bytes) != trusted_policy_sha256:
            raise ValueError("trusted policy pin mismatch")
        doc = _parse_strict(policy_bytes)
        if not isinstance(doc, dict) or set(doc) != POLICY_FIELDS:
            raise ValueError("trusted policy schema")
        if type(doc["schema_version"]) is not int or doc["schema_version"] != 1:
            raise ValueError("trusted policy schema_version")
        if type(doc["min_version"]) is not int or doc["min_version"] < 1:
            raise ValueError("trusted min_version")
        for name in ("dataset_id", "signer_id"):
            if not isinstance(doc[name], str) or not doc[name]:
                raise ValueError("trusted policy identity")
        for name in ("public_key_sha256", "checkpoint_sha256"):
            if not isinstance(doc[name], str) or not HEX64.fullmatch(doc[name]):
                raise ValueError("trusted policy digest")
        key_bytes = pathlib.Path(public_key).read_bytes()
        cp_bytes = pathlib.Path(checkpoint).read_bytes()
        if _hash(key_bytes) != doc["public_key_sha256"]:
            raise ValueError("public key differs from trusted policy")
        if _hash(cp_bytes) != doc["checkpoint_sha256"]:
            raise ValueError("replay checkpoint differs from trusted policy")
        cp = _parse_strict(cp_bytes)
        if not isinstance(cp, dict) or set(cp) != {"dataset_id", "signer_id", "min_version"}:
            raise ValueError("checkpoint schema")
        if any(cp.get(name) != doc[name] or type(cp.get(name)) is not type(doc[name])
               for name in ("dataset_id", "signer_id", "min_version")):
            raise ValueError("checkpoint differs from pinned policy fields")
        # Verify with captured bytes instead of re-reading mutable trust inputs.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            fixed_key = root / "public.pem"
            fixed_cp = root / "checkpoint.json"
            fixed_key.write_bytes(key_bytes)
            fixed_cp.write_bytes(cp_bytes)
            result = verify(manifest, ledger, signature, fixed_key, fixed_cp, now=now)
        output["anchor_consistent"] = True
        output["integrity_pass"] = bool(result["integrity_pass"])
        output["signature_valid"] = bool(result["signature_valid"])
        output["replay_rejected"] = bool(result["replay_rejected"])
        output["reason"] = result.get("reason", "delegated signed ledger failure")
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        output["reason"] = str(exc)
    # Even when inputs match, the caller may control the pin. Never claim
    # source provenance, training approval or operational promotion here.
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "ledger", "signature", "public_key", "checkpoint", "policy"):
        parser.add_argument("--" + name.replace("_", "-"), required=True)
    parser.add_argument("--trusted-policy-sha256", required=True,
                        help="Must be supplied from a separately controlled trusted channel")
    a = parser.parse_args()
    result = verify_anchored(a.manifest, a.ledger, a.signature, a.public_key,
                             a.checkpoint, a.policy, a.trusted_policy_sha256)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if result["integrity_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
