#!/usr/bin/env python3
"""Offline signed dataset ledger check. Experimental only: never authorizes training."""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timezone

def strict_json(path):
    def pairs(items):
        obj = {}
        for k, v in items:
            if k in obj:
                raise ValueError("duplicate JSON key")
            obj[k] = v
        return obj
    def reject(value):
        raise ValueError("nonfinite JSON value")
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=pairs, parse_constant=reject)

def verify(manifest, ledger, signature, public_key, checkpoint, now=None):
    """Return fail-closed evidence; caller must independently control key/checkpoint."""
    result = {"integrity_pass": False, "signature_valid": False,
              "replay_rejected": False, "provenance_verified": False,
              "training_approved": False, "promotion_approved": False}
    try:
        doc = strict_json(ledger)
        cp = strict_json(checkpoint)
        required = {"dataset_id", "manifest_sha256", "version", "signer_id",
                    "schema_version", "expires_at"}
        if not isinstance(doc, dict) or set(doc) != required:
            raise ValueError("ledger schema")
        if not isinstance(cp, dict) or set(cp) != {"dataset_id", "min_version", "signer_id"}:
            raise ValueError("checkpoint schema")
        if not isinstance(doc["dataset_id"], str) or not doc["dataset_id"]:
            raise ValueError("dataset id")
        if not isinstance(doc["signer_id"], str) or not doc["signer_id"]:
            raise ValueError("signer id")
        if type(doc["version"]) is not int or doc["version"] < 1:
            raise ValueError("version")
        if type(cp["min_version"]) is not int or cp["min_version"] < 1:
            raise ValueError("checkpoint version")
        if doc["schema_version"] != 1:
            raise ValueError("schema version")
        if not isinstance(doc["manifest_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", doc["manifest_sha256"]):
            raise ValueError("manifest hash")
        if doc["dataset_id"] != cp["dataset_id"] or doc["signer_id"] != cp["signer_id"]:
            raise ValueError("untrusted identity")
        if not isinstance(doc["expires_at"], str):
            raise ValueError("expiry")
        expiry = datetime.fromisoformat(doc["expires_at"].replace("Z", "+00:00"))
        if expiry.tzinfo is None or expiry <= (now or datetime.now(timezone.utc)):
            raise ValueError("expired")
        if doc["version"] < cp["min_version"]:
            result["replay_rejected"] = True
            raise ValueError("replayed ledger")
        canonical = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        # Signature is over canonical JSON, not the mutable original file encoding.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            payload = pathlib.Path(tmp) / "payload"
            payload.write_bytes(canonical)
            checked = subprocess.run(["openssl", "dgst", "-sha256", "-verify",
                                      str(pathlib.Path(public_key).resolve()), "-signature",
                                      str(pathlib.Path(signature).resolve()), str(payload)],
                                     capture_output=True, timeout=10, check=False)
            if checked.returncode != 0:
                raise ValueError("signature verification failed")
        result["signature_valid"] = True
        actual = hashlib.sha256(pathlib.Path(manifest).read_bytes()).hexdigest()
        if actual != doc["manifest_sha256"]:
            raise ValueError("manifest hash mismatch")
        result["integrity_pass"] = True
        result["reason"] = "signed ledger and externally supplied checkpoint match; provenance NOT certified"
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired) as exc:
        result["reason"] = str(exc)
    return result

def main():
    p = argparse.ArgumentParser()
    for name in ("manifest", "ledger", "signature", "public_key", "checkpoint"):
        p.add_argument("--" + name.replace("_", "-"), required=True)
    a = p.parse_args()
    result = verify(a.manifest, a.ledger, a.signature, a.public_key, a.checkpoint)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["integrity_pass"] else 1

if __name__ == "__main__":
    sys.exit(main())
