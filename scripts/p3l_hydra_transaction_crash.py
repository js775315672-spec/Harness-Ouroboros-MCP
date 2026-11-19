"""Crash the Hydra SQLite writer at the real transaction commit boundary."""
from contextlib import closing
import json
import signal
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, "scripts")
from p3l_hydra_completion_rehearsal import CompletionRegistry
from p3l_hydra_generation_rehearsal import make_plan

HEAD = "900fbd4292bdd258b8b619c055e62fbd7383dc21"
TREE = "e36d27867b93d7e6bd64009b8917ef9cc5a75a2f"
SOURCE = dict(task="source", head=HEAD, run_id=1, job_id=1)
SCOPE = ("first", "second")


def proof(event):
    return {**event, "passed": True, "sha256": "a" * 64}


def worker(path, operation, boundary):
    registry = CompletionRegistry(path, make_plan(HEAD), approved_tasks=SCOPE)
    connect = sqlite3.connect

    class PausedCommit(sqlite3.Connection):
        def __exit__(self, *exc):
            assert exc[0] is None and self.in_transaction
            if boundary == "after_commit":
                super().__exit__(*exc)
            path.with_suffix(".ready").touch()
            time.sleep(60)
            raise RuntimeError("parent did not terminate the worker")

    sqlite3.connect = lambda *args, **kwargs: connect(*args, factory=PausedCommit, **kwargs)
    if operation == "complete":
        registry.complete(SOURCE, proof)
    else:
        registry.consume("first", SOURCE, observed_head=HEAD, completion=(1, 2))


def verify():
    assert subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], text=True).strip() == TREE
    assert not subprocess.check_output(["git", "status", "--porcelain"])
    results = []
    with tempfile.TemporaryDirectory() as temp:
        for operation in ("complete", "consume"):
            for boundary in ("before_commit", "after_commit"):
                path = Path(temp) / f"{operation}-{boundary}.sqlite"
                registry = CompletionRegistry(path, make_plan(HEAD), approved_tasks=SCOPE)
                if operation == "consume":
                    assert registry.complete(SOURCE, proof)["reserved"] == ["first"]
                with subprocess.Popen([sys.executable, "-B", __file__, str(path), operation, boundary]) as proc:
                    try:
                        until = time.monotonic() + 10
                        while not path.with_suffix(".ready").exists() and proc.poll() is None:
                            assert time.monotonic() < until
                            time.sleep(.02)
                        assert proc.poll() is None
                    finally:
                        if proc.poll() is None:
                            proc.kill()
                        proc.wait(timeout=10)
                    assert proc.returncode == -signal.SIGKILL
                recovered = CompletionRegistry(path, make_plan(HEAD), approved_tasks=SCOPE)
                committed = boundary == "after_commit"
                with closing(sqlite3.connect(path)) as db:
                    assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
                    if operation == "complete":
                        for table in ("receipts", "reservations"):
                            assert db.execute(f"SELECT task FROM {table}").fetchall() == (
                                [("source" if table == "receipts" else "first",)] if committed else [])
                        plan, = db.execute("SELECT data FROM plan WHERE id=1").fetchone()
                        assert json.loads(plan)["tasks"][0]["state"] == ("passed" if committed else "running")
                    else:
                        for table in ("starts", "expected_completions"):
                            assert db.execute(f"SELECT task FROM {table}").fetchall() == (
                                [("first",)] if committed else [])
                if operation == "complete":
                    assert recovered.complete(SOURCE, proof)["accepted"] is not committed
                    assert not recovered.complete(SOURCE, proof)["accepted"]
                else:
                    assert recovered.consume("first", SOURCE, observed_head=HEAD, completion=(1, 2)) is not committed
                    assert not recovered.consume("first", SOURCE, observed_head=HEAD, completion=(1, 2))
                results.append(dict(operation=operation, boundary=boundary, exit_code=proc.returncode,
                                    integrity="ok", expected_recovery=True))
    print(json.dumps(dict(head=HEAD, tree=TREE, platform=sys.platform, cases=results,
                          completion_proof="fixture", model_calls=0), indent=2))


if __name__ == "__main__":
    if len(sys.argv) == 4:
        worker(Path(sys.argv[1]), *sys.argv[2:])
    else:
        verify()
