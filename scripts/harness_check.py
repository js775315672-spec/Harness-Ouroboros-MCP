#!/usr/bin/env python3
"""Read-only secret scan of tracked repository files; no network or dependencies."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

SIGNATURES = {
    "private key": rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----",
    "github token": rb"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b",
    "aws access key": rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
    "google api key": rb"\bAIza[0-9A-Za-z_-]{35}\b",
    "slack token": rb"\bxox[baprs]-[A-Za-z0-9-]{15,}\b",
    "stripe secret key": rb"\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b",
    "generic credential assignment": rb"(?i)(?:api[_-]?key|secret|access[_-]?token|password)\s*[:=]\s*['\"][^'\"\r
]{12,}['\"]",
}
PATTERNS = {name: re.compile(expr) for name, expr in SIGNATURES.items()}
CHUNK = 1024 * 1024
OVERLAP = 512
EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__"}

def tracked_files(root):
    result = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                            capture_output=True, check=True)
    return [Path(os.fsdecode(p)) for p in result.stdout.split(b"\0") if p]

def scan(root):
    findings = []
    failures = []
    for rel in tracked_files(root):
        if any(part in EXCLUDED for part in rel.parts):
            continue
        if rel.as_posix() in {"scripts/harness_check.py", "tests/test_harness_check.py"}:
            continue  # scanner signatures and synthetic test fixtures only
        path = root / rel
        try:
            if path.is_symlink():
                failures.append(f"{rel}: symbolic link requires review")
                continue
            with path.open("rb") as stream:
                prefix = b""
                while True:
                    chunk = stream.read(CHUNK)
                    if not chunk:
                        break
                    data = prefix + chunk
                    if b"\0" in data:
                        failures.append(f"{rel}: binary content requires separate review")
                        break
                    for name, pattern in PATTERNS.items():
                        if pattern.search(data):
                            findings.append(f"{rel}: possible {name}")
                    prefix = data[-OVERLAP:]
        except (OSError, ValueError) as exc:
            failures.append(f"{rel}: unable to inspect ({type(exc).__name__})")
    return sorted(set(findings)), sorted(set(failures))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        findings, failures = scan(args.root.resolve())
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: cannot enumerate tracked files: {type(exc).__name__}")
        return 2
    for message in findings:
        print("SECRET:", message)
    for message in failures:
        print("UNSCANNED:", message)
    print(f"Harness scan: {len(findings)} findings; {len(failures)} inspection failures")
    return 1 if findings or failures else 0

if __name__ == "__main__":
    sys.exit(main())
