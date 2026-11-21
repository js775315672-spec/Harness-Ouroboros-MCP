import concurrent.futures
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from cycle_registry import Blocked, git, transact


class RegistryTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.remote = str(pathlib.Path(temp.name) / "origin.git")
        git("init", "--quiet", "--bare", self.remote)
        self.source = git("rev-parse", "HEAD")
        git("push", self.remote, self.source + ":refs/heads/main")

    def call(self, command, owner="slot", gen=1, value=""):
        return transact(self.remote, command, owner, gen, self.source, value)

    def test_ten_contenders(self):
        def acquire(i):
            try:
                return self.call("acquire", str(i))["owner"]
            except (Blocked, subprocess.CalledProcessError):
                return None

        with concurrent.futures.ThreadPoolExecutor(10) as pool:
            winners = [owner for owner in pool.map(acquire, range(10)) if owner is not None]
        self.assertEqual(winners, [self.call("inspect")["owner"]])

    def test_recover_and_fence(self):
        with patch("cycle_registry.time.time", return_value=100):
            initial = self.call("acquire")
            self.call("checkpoint", value="tested")
        resumed = self.call("acquire", owner="next")
        self.assertEqual((resumed["cycle"], resumed["checkpoint"]), (initial["cycle"], "tested"))
        with self.assertRaises(Blocked):
            self.call("complete")
        self.call("complete", "next", 2)

    def test_crash_after_external_effect(self):
        with patch("cycle_registry.time.time", return_value=100):
            self.call("acquire")
            self.call("reserve", value="model-1")
        with self.assertRaisesRegex(Blocked, "unresolved"):
            self.call("acquire", "next")
        self.assertEqual(self.call("inspect")["pending"], "model-1")

    def test_recorded_effect_and_source_conflict(self):
        self.call("acquire")
        for key in ("pr", "model", "artifact"):
            self.call("reserve", value=key)
            self.call("record", value=key + "=receipt")
            with self.assertRaises(Blocked):
                self.call("reserve", value=key)
        before = self.call("inspect")
        with self.assertRaises(Blocked):
            transact(self.remote, "complete", "slot", 1, "wrong")
        self.assertEqual(self.call("inspect"), before)
        self.call("stop")
        with self.assertRaises(Blocked):
            self.call("acquire", "next")


if __name__ == "__main__":
    unittest.main()
