"""Rehearse separate clients, transport errors, and W06 admission on loopback."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, replace
from http.client import HTTPConnection, RemoteDisconnected
import json
from pathlib import Path
import sys
import tempfile
from threading import Barrier, Thread
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from p3l_w04_attempt_registry import AttemptBlocked, AttemptInput, AttemptRegistry
from p3l_w04_local_service import LOOPBACK, RegistryClient, RegistryServer, _RegistryHandler
from p3l_w05_actions_source import QWEN_REVISION, QWEN_WEIGHTS_SHA256
import p3l_w06_actual_model_once as w06

HEAD = "2" * 40
PARENT = "1" * 40
MODEL = {"revision": QWEN_REVISION, "sha256": QWEN_WEIGHTS_SHA256}
TASK = AttemptInput("ledger-validation", "a" * 64, PARENT, HEAD, QWEN_REVISION,
                    QWEN_WEIGHTS_SHA256, "b" * 64, "c" * 64)


@contextmanager
def serving(registry):
    with RegistryServer(registry) as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            thread.join(timeout=5)


class RegistryServiceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "attempts.sqlite3"
        self.now = 100
        self.registry = AttemptRegistry(self.path, clock=lambda: self.now)

    def test_independent_clients_share_one_admission_across_server_restart(self):
        barrier = Barrier(2)
        with serving(self.registry) as port, ThreadPoolExecutor(max_workers=2) as pool:
            def worker(owner):
                client = RegistryClient(port)
                barrier.wait(timeout=5)
                try:
                    lease = client.reserve(TASK, owner, ttl_seconds=20)
                    client.start(lease, observed_head=HEAD, run_id=123)
                except AttemptBlocked:
                    return False
                return True

            self.assertCountEqual(list(pool.map(worker, ["worker-a", "worker-b"])), [True, False])
        self.now = 121
        reopened = AttemptRegistry(self.path, clock=lambda: self.now)
        with serving(reopened) as port:
            client = RegistryClient(port)
            self.assertEqual(client.status(TASK)["state"], "UNVERIFIED")
            with self.assertRaises(AttemptBlocked):
                client.reserve(TASK, "worker-c", ttl_seconds=20)

    def test_nonlocal_origin_is_rejected_before_reserving(self):
        with serving(self.registry) as port:
            conn = HTTPConnection(LOOPBACK, port, timeout=5)
            try:
                payload = json.dumps({"inputs": asdict(TASK), "owner": "worker", "ttl_seconds": 20})
                conn.request("POST", "/reserve", payload,
                             {"Content-Type": "application/json", "Origin": "https://example.com"})
                response = conn.getresponse()
                self.assertEqual(response.status, 400)
                response.read()
            finally:
                conn.close()
        self.assertIsNone(self.registry.status(TASK))

    def test_w06_managed_path_checks_input_and_spends_budget_before_inference(self):
        invoke = Mock(return_value=("def validate(records):\n    return len(records)\n", 0.1))
        def git(argv, **kwargs):
            return Mock(stdout=PARENT + "\n" if argv[-1].endswith("^") else HEAD + "\n")

        with serving(self.registry) as port, patch.object(w06.subprocess, "run", side_effect=git), \
             patch.object(w06.p3g, "check_model", return_value=MODEL):
            client = RegistryClient(port)
            inputs = w06.managed_attempt_input(ROOT, HEAD, w06.w02.build(ROOT), MODEL)
            mismatched = replace(inputs, task_type="different-task", prompt_sha256="d" * 64)
            wrong = client.reserve(mismatched, "other-worker", ttl_seconds=20)
            lease = client.reserve(inputs, "worker", ttl_seconds=20)
            args = ROOT, HEAD, 123, Path("binary"), Path("weights"), Path("metadata")
            with self.assertRaisesRegex(AttemptBlocked, "does not match"):
                w06.execute(*args, infer_fn=invoke, admission=(client, wrong))
            invoke.assert_not_called()
            result = w06.execute(*args, infer_fn=invoke, admission=(client, lease))
            with self.assertRaises(AttemptBlocked):
                w06.execute(*args, infer_fn=invoke, admission=(client, lease))
        invoke.assert_called_once()
        self.assertEqual(result["prompt_sha256"], inputs.prompt_sha256)
        self.assertEqual(self.registry.status(inputs)["run_id"], 123)

    def test_lost_start_acknowledgement_does_not_invoke_w06(self):
        invoke = Mock()
        def git(argv, **kwargs):
            return Mock(stdout=PARENT + "\n" if argv[-1].endswith("^") else HEAD + "\n")

        original_reply = _RegistryHandler._reply
        def drop_start_ack(handler, status, payload):
            if handler.path == "/start" and status == 200:
                return
            original_reply(handler, status, payload)

        with serving(self.registry) as port, patch.object(w06.subprocess, "run", side_effect=git), \
             patch.object(w06.p3g, "check_model", return_value=MODEL), \
             patch.object(_RegistryHandler, "_reply", drop_start_ack):
            client = RegistryClient(port)
            inputs = w06.managed_attempt_input(ROOT, HEAD, w06.w02.build(ROOT), MODEL)
            lease = client.reserve(inputs, "worker", ttl_seconds=20)
            args = ROOT, HEAD, 123, Path("binary"), Path("weights"), Path("metadata")
            with self.assertRaises(RemoteDisconnected):
                w06.execute(*args, infer_fn=invoke, admission=(client, lease))
            with self.assertRaises(AttemptBlocked):
                w06.execute(*args, infer_fn=invoke, admission=(client, lease))
        invoke.assert_not_called()
        self.assertEqual(self.registry.status(inputs)["state"], "STARTED")


if __name__ == "__main__":
    unittest.main()
