"""Independently grade one proposed W08 test without executing it on the host."""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import zipfile

from disposable_regression_compare import _docker_command
from p3l_w07_revision_isolation import CANDIDATE_COMMIT, git

TARGET = Path("tests/test_resumable_task_queue.py")
QUEUE = Path("scripts/resumable_task_queue.py")
METHOD = "test_concurrent_checkpoint_cas"
STALE_CHECK = b'elif load(path)["integrity"] != expected_integrity:'
IMPORTS = {
    "concurrent.futures": {"ThreadPoolExecutor"},
    "threading": {"Barrier", "Event"},
}
CALLS = {
    "Path", "TemporaryDirectory", "ThreadPoolExecutor", "Barrier", "Event",
    "advance", "evidence", "github_ok", "load", "new_queue", "save", "str",
}
ATTRIBUTES = {
    "TemporaryDirectory", "assertEqual", "assertFalse", "assertRaises", "assertRaisesRegex",
    "assertTrue", "exists", "result", "set", "submit", "wait", "with_name",
}
SYNTAX = (
    ast.FunctionDef, ast.arguments, ast.arg, ast.ImportFrom, ast.alias, ast.With,
    ast.withitem, ast.Assign, ast.Expr, ast.Call, ast.keyword, ast.Name, ast.Load,
    ast.Store, ast.Attribute, ast.Constant, ast.BinOp, ast.Div, ast.Mult, ast.Subscript,
    ast.Tuple, ast.List, ast.Dict, ast.Try, ast.ExceptHandler, ast.Return, ast.Raise, ast.If,
    ast.Compare, ast.Eq, ast.NotEq, ast.Is, ast.IsNot, ast.UnaryOp, ast.Not, ast.Pass,
    ast.Assert, ast.BoolOp, ast.And,
)


def check_method(method, *, extra_calls=()):
    for node in ast.walk(method):
        if not isinstance(node, SYNTAX):
            raise ValueError("unsupported syntax in W08 test")
        if isinstance(node, ast.ImportFrom) and (
            node.level or any(alias.asname or alias.name not in IMPORTS.get(node.module, set())
                              for alias in node.names)
        ):
            raise ValueError("unsupported import in W08 test")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ValueError("private names are unavailable to W08 tests")
        if isinstance(node, ast.Attribute) and (node.attr not in ATTRIBUTES or not isinstance(node.ctx, ast.Load)):
            raise ValueError("unsupported attribute in W08 test")
        if isinstance(node, ast.Subscript) and not isinstance(node.ctx, ast.Load):
            raise ValueError("W08 tests may not replace checkpoint fields")
        if isinstance(node, ast.FunctionDef) and (node.decorator_list or node.returns is not None):
            raise ValueError("W08 test helpers may not have decorators or annotations")
        if isinstance(node, ast.Call) and (
            not isinstance(node.func, (ast.Attribute, ast.Name))
            or isinstance(node.func, ast.Name)
            and node.func.id not in CALLS and node.func.id not in extra_calls and not node.func.id.startswith("writer_")
        ):
            raise ValueError("unsupported call in W08 test")


def unwrap_proposal(raw):
    """Allow one exact Python envelope while retaining the raw model evidence."""
    if not 1 <= len(raw) <= 6000:
        raise ValueError("invalid W08 proposal size")
    lines = raw.strip().splitlines(keepends=True)
    if lines[0].rstrip(b"\r\n") != b"```python" or lines[-1].rstrip(b"\r\n") != b"```":
        return raw
    body = b"".join(lines[1:-1])
    if not body.strip() or any(line.lstrip().startswith(b"```") for line in lines[1:-1]):
        raise ValueError("invalid W08 Python envelope")
    return body


def append_test(original, proposal, *, method_name=METHOD, extra_calls=()):
    if not 1 <= len(proposal) <= 6000:
        raise ValueError("invalid W08 proposal size")
    source = textwrap.dedent(proposal.decode("utf-8")).strip()
    nodes = ast.parse(source).body
    if len(nodes) != 1 or type(nodes[0]) is not ast.FunctionDef:
        raise ValueError("expected a single W08 test method")
    method = nodes[0]
    args = method.args
    if (method.name != method_name or method.decorator_list or method.returns is not None
            or [arg.arg for arg in args.args] != ["self"] or args.args[0].annotation is not None
            or args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg or args.defaults):
        raise ValueError("invalid W08 test signature")
    check_method(method, extra_calls=extra_calls)
    marker = b'\n\nif __name__ == "__main__":'
    if original.count(marker) != 1:
        raise ValueError("reviewed test module entry point changed")
    addition = ("\n\n" + textwrap.indent(source, "    ")).encode("utf-8")
    combined = original.replace(marker, addition + marker)
    ast.parse(combined)
    return combined


def verify(root, proposal, *, checkpoint_attestation=False):
    base = CANDIDATE_COMMIT
    method, anchor, replacement = METHOD, STALE_CHECK, b"elif False:"
    extra_calls = ()
    extra_mutations = []
    if checkpoint_attestation:
        base = "bb1a446473dfcd150c5161461c14a9420835d60b"
        method = "test_checkpoint_rejects_wrong_attestation"
        anchor = b'data.get("name") != "Harness safety checks"'
        replacement = b"False"
        extra_calls = ("dict",)
        advance_anchor = b'    event = {"seq": record["generation"] + 1,'
        save_anchor = b"def save(path, record, expected_integrity=None):\n"
        extra_mutations = [
            ("no_advance", advance_anchor, b"    if passed:\n        return record\n" + advance_anchor),
            ("no_persist", save_anchor, save_anchor + b"    if expected_integrity is not None:\n        return\n"),
        ]
    if git(root, "rev-parse", "HEAD").decode().strip() != base:
        raise ValueError("W08 requires the exact reviewed checkout")
    archive = git(root, "archive", "--format=zip", base, "scripts", "tests")
    with tempfile.TemporaryDirectory(prefix="w08-test-") as directory:
        root = Path(directory)
        root.chmod(0o755)
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            zipped.extractall(root)
        for path in root.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
        target = root / TARGET
        normalized = unwrap_proposal(proposal)
        candidate = append_test(target.read_bytes(), normalized, method_name=method, extra_calls=extra_calls)
        target.write_bytes(candidate)
        queue = root / QUEUE
        original = queue.read_bytes()

        def run(args):
            command = _docker_command(root, "python:3.11-slim", args)
            return subprocess.run(command, capture_output=True, text=True, timeout=100, check=False)

        clean = run(["-m", "unittest", "discover", "-s", "tests", "-p", TARGET.name, "-v"])
        if (clean.returncode != 0 or not re.search(r"(?m)^Ran 7 tests? ", clean.stderr)
                or not re.search(rf"(?m)^{method} .* \.\.\. ok$", clean.stderr)):
            raise ValueError("candidate must pass all seven tests in Docker")
        digests = {}
        for name, old, new in [("wrong_evidence", anchor, replacement), *extra_mutations]:
            if original.count(old) != 1:
                raise ValueError("pinned mutation anchor changed")
            mutant = original.replace(old, new)
            queue.write_bytes(mutant)
            altered = run(["-c", "import sys,unittest;sys.path.insert(0,'tests');unittest.main(module=None)",
                           "-v", f"test_resumable_task_queue.ResumableQueueTests.{method}"])
            if (altered.returncode != 1 or not re.search(r"(?m)^Ran 1 test ", altered.stderr)
                    or not re.search(rf"(?m)^FAIL: {method} ", altered.stderr)
                    or "FAILED (failures=1)" not in altered.stderr):
                raise ValueError(f"the proposed test must fail by assertion on the selected mutant: {name}")
            digests[name] = hashlib.sha256(mutant).hexdigest()
    return {"base_sha": base, "target": TARGET.as_posix(),
            "proposal_sha256": hashlib.sha256(proposal).hexdigest(),
            "normalized_proposal_sha256": hashlib.sha256(normalized).hexdigest(),
            "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
            "mutant_sha256": digests["wrong_evidence"],
            **({"mutants": digests} if checkpoint_attestation else {}),
            "normal_test_count": 7, "mutant_assertion_failures": len(digests)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--checkpoint-attestation", action="store_true")
    args = parser.parse_args()
    with args.proposal.open("rb") as stream:
        proposal = stream.read(6001)
    print(json.dumps(verify(args.checkout, proposal, checkpoint_attestation=args.checkpoint_attestation), sort_keys=True))


if __name__ == "__main__":
    main()
