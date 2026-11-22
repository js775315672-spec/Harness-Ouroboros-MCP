"""Live local Git CAS integration; never touches GitHub production registry."""
import hashlib
import io
import json
import os
import subprocess
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from agent import cycle_registry as registry
from agent.pending_reconcile import Observation
from agent.verified_pending_cas import verified_receipt, reconcile_to_isolated_remote

def git(*args, cwd=None):
    return subprocess.run(["git", *map(str, args)], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()

class VerifiedPendingCASTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.remote = str(root / "isolated.git")
        self.work = root / "work"
        git("init", "--bare", self.remote)
        git("init", self.work)
        git("config", "user.name", "test", cwd=self.work)
        git("config", "user.email", "test@example.invalid", cwd=self.work)
        (self.work / "seed").write_text("source")
        git("add", ".", cwd=self.work)
        git("commit", "-m", "seed", cwd=self.work)
        git("branch", "-M", "main", cwd=self.work)
        git("remote", "add", "origin", self.remote, cwd=self.work)
        git("push", "origin", "main", cwd=self.work)
        self.source = git("rev-parse", "HEAD", cwd=self.work)
        old = os.getcwd()
        os.chdir(self.work)
        self.addCleanup(os.chdir, old)
        self.owner = "dev-test"
        self.pending = "artifact:123"
        acquired = registry.transact(self.remote, "acquire",
                                     owner=self.owner, source=self.source, ttl=600)
        self.generation = acquired["generation"]
        registry.transact(self.remote, "reserve", owner=self.owner,
                          generation=self.generation, source=self.source,
                          value=self.pending)
        self.now = time.time()
        self.receipt = '{"verified":true}'
        self.observation = Observation(self.pending, self.source,
                                       "confirmed", self.receipt)

    def commit(self, *, lookup=None, verify=None, generation=None):
        return reconcile_to_isolated_remote(
            self.remote, owner=self.owner,
            generation=self.generation if generation is None else generation,
            source=self.source, now=self.now,
            lookup=lookup or (lambda key: self.observation),
            verify=verify or (lambda observation: observation == self.observation),
            expected_pending=self.pending)

    def test_real_remote_receipt_commit_and_restart(self):
        result = self.commit()
        self.assertIsNone(result["pending"])
        self.assertEqual(result["results"][self.pending], self.receipt)
        # Fresh Git remote read after restart, no in-memory state assumption.
        restarted = registry.transact(self.remote, "inspect")
        self.assertEqual(restarted["results"], result["results"])
        with self.assertRaises(registry.Blocked):
            self.commit()
        self.assertEqual(registry.transact(self.remote, "inspect"), restarted)

    def test_forged_receipt_rejected_without_mutation(self):
        before = registry.transact(self.remote, "inspect")
        with self.assertRaises(registry.Blocked):
            self.commit(verify=lambda _: False)
        self.assertEqual(registry.transact(self.remote, "inspect"), before)

    def test_stale_generation_rejected_without_mutation(self):
        before = registry.transact(self.remote, "inspect")
        with self.assertRaises(registry.Blocked):
            self.commit(generation=self.generation - 1)
        self.assertEqual(registry.transact(self.remote, "inspect"), before)

    def test_unknown_external_outcome_keeps_pending(self):
        before = registry.transact(self.remote, "inspect")
        with self.assertRaises(registry.Blocked):
            self.commit(lookup=lambda _: None)
        self.assertEqual(registry.transact(self.remote, "inspect"), before)

    def test_production_remote_rejected(self):
        with self.assertRaises(registry.Blocked):
            reconcile_to_isolated_remote(registry.REMOTE, owner=self.owner,
                generation=self.generation, source=self.source, now=self.now,
                lookup=lambda _: self.observation, verify=lambda _: True,
                expected_pending=self.pending)

    def test_real_zip_bytes_digest_and_forgery(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as z:
            z.writestr("provenance.txt", "pinned evidence")
        data = stream.getvalue()
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        artifact = {"id": 123, "digest": digest, "expired": False,
                    "size_in_bytes": len(data),
                    "workflow_run": {"id": 456, "head_sha": self.source}}
        kwargs = dict(repo="example/isolated", run_id=456,
                      head_sha=self.source, fetch=lambda _: data)
        receipt = json.loads(verified_receipt(artifact, **kwargs))
        self.assertEqual(receipt["digest"], digest)
        self.assertEqual(receipt["artifact_id"], 123)
        artifact["digest"] = "sha256:" + "0" * 64
        with self.assertRaises(registry.Blocked):
            verified_receipt(artifact, **kwargs)


    def test_expired_lease_preserves_pending_and_blocks_record(self):
        from unittest.mock import patch
        before = registry.transact(self.remote, "inspect")
        with patch.object(registry.time, "time", return_value=before["expires"] + 1):
            with self.assertRaises(registry.Blocked):
                self.commit()
            with self.assertRaises(registry.Blocked):
                registry.transact(self.remote, "recover", owner="new-owner",
                    generation=self.generation, source=self.source, ttl=600)
        self.assertEqual(registry.transact(self.remote, "inspect"), before)

    def test_duplicate_receipt_after_restart_cannot_rewrite(self):
        first = self.commit()
        original_ref = git("ls-remote", self.remote, registry.REF)
        for _ in range(2):
            with self.assertRaises(registry.Blocked):
                self.commit()
        self.assertEqual(git("ls-remote", self.remote, registry.REF), original_ref)
        self.assertEqual(registry.transact(self.remote, "inspect"), first)

    def test_concurrent_processes_only_one_cas_receipt_wins(self):
        # Separate Git checkouts and OS processes: no shared cwd or Python state.
        from concurrent.futures import ThreadPoolExecutor
        from pathlib import Path
        import sys
        import textwrap
        root = Path(self.tmp.name)
        script = root / "worker.py"
        script.write_text(textwrap.dedent("""
            import os, sys, json
            sys.path.insert(0, sys.argv[1])
            from agent import cycle_registry as registry
            from agent.pending_reconcile import Observation
            from agent.verified_pending_cas import reconcile_to_isolated_remote
            remote, owner, generation, source, pending = sys.argv[2:]
            observation = Observation(pending, source, "confirmed", '{"verified":true}')
            try:
                result = reconcile_to_isolated_remote(remote, owner=owner,
                    generation=int(generation), source=source, now=__import__("time").time(),
                    lookup=lambda _: observation, verify=lambda _: True,
                    expected_pending=pending)
                print("WIN", result["results"][pending])
            except (registry.Blocked, subprocess.CalledProcessError) as exc:
                print("BLOCKED", type(exc).__name__)
        """).replace("import os, sys, json", "import os, sys, json, subprocess"))
        source_root = str(Path(__file__).resolve().parents[1])
        def contender(index):
            clone = root / ("contender-" + str(index))
            git("clone", "--quiet", self.remote, clone)
            git("checkout", "-q", "main", cwd=clone)
            return subprocess.run([sys.executable, str(script), source_root,
                self.remote, self.owner, str(self.generation), self.source,
                self.pending], cwd=clone, text=True, capture_output=True,
                timeout=30)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(contender, (1, 2)))
        for result in outcomes:
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sum("WIN " in r.stdout for r in outcomes), 1,
                         [(r.stdout, r.stderr) for r in outcomes])
        self.assertEqual(sum("BLOCKED " in r.stdout for r in outcomes), 1)
        final = registry.transact(self.remote, "inspect")
        self.assertIsNone(final["pending"])
        self.assertEqual(final["results"][self.pending], self.receipt)

if __name__ == "__main__":
    unittest.main()
