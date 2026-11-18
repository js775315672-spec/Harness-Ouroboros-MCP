"""Rehearse separate clients, transport errors, and W06 admission on loopback."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, redirect_stdout
from dataclasses import asdict, replace
from http.client import HTTPConnection, RemoteDisconnected
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
from threading import Barrier, Lock, Thread
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from p3l_w04_attempt_registry import AttemptBlocked, AttemptInput, AttemptRegistry
from p3l_w04_github_claim import SharedBudget, START_REF_PREFIX
from p3l_w04_local_service import LOOPBACK, RegistryClient, RegistryServer, _RegistryHandler
from p3l_w05_actions_source import QWEN_REVISION, QWEN_WEIGHTS_SHA256
import p3l_w06_actual_model_once as w06

HEAD = "2" * 40
PARENT = "1" * 40
MODEL = {"revision": QWEN_REVISION, "sha256": QWEN_WEIGHTS_SHA256}
TASK = AttemptInput("ledger-validation", "a" * 64, PARENT, HEAD, QWEN_REVISION,
                    QWEN_WEIGHTS_SHA256, "b" * 64, "c" * 64)


@contextmanager
def serving(registry, *, shared_budget=None):
    with RegistryServer(registry, shared_budget=shared_budget) as server:
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


class SharedAdmissionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.now = 100
        self.build = w06.w02.build(ROOT)
        self.enterContext(patch.object(w06.subprocess, "run", side_effect=lambda argv, **kw:
                          Mock(stdout=PARENT + "\n" if argv[-1].endswith("^") else HEAD + "\n")))
        self.enterContext(patch.object(w06.p3g, "check_model", return_value=MODEL))
        rehearsal = {**self.build, "w01_provisional_spec_sha256": "f" * 64}
        self.enterContext(patch.object(w06.w02, "build", return_value=rehearsal))
        self.inputs = w06.managed_attempt_input(ROOT, HEAD, rehearsal, MODEL)
        self.provider = {}
        self.lock = Lock()
        self.drop_ack = False
        self.request = Mock(side_effect=self.request_ref)
        self.infer = Mock(return_value=("def validate(records):\n    return len(records)\n", 0.1))

    def request_ref(self, method, route, payload=None):
        with self.lock:
            if method == "POST":
                ref = json.loads(payload)
                name = ref["ref"]
                if name in self.provider:
                    return 422, b"{}"
                self.provider[name] = ref["sha"]
                if self.drop_ack:
                    raise TimeoutError("provider acknowledgement lost")
                code = 201
            else:
                name = "refs/" + route.removeprefix("/ref/")
                code = 200
            return code, json.dumps({"ref": name, "object": {"type": "commit", "sha": self.provider[name]}})

    def registry(self, name):
        return AttemptRegistry(self.root / name, clock=lambda: self.now)

    def budget(self, run_id):
        return SharedBudget(self.inputs, run_id, self.request)

    def attempt(self, port, run_id, *, lease=None):
        client = RegistryClient(port, require_shared=True)
        if lease is None:
            lease = client.reserve(self.inputs, "coordinator", ttl_seconds=20)
        return w06.execute(ROOT, HEAD, run_id, Path("binary"), Path("weights"), Path("metadata"),
                           infer_fn=self.infer, admission=(client, lease))

    def test_distinct_coordinators_share_one_model_budget(self):
        barrier = Barrier(2)

        def worker(port, run_id):
            barrier.wait(timeout=5)
            try:
                self.attempt(port, run_id)
            except AttemptBlocked:
                return False
            return True

        with serving(self.registry("first.sqlite3"), shared_budget=self.budget(123)) as first, \
             serving(self.registry("second.sqlite3"), shared_budget=self.budget(124)) as second, \
             ThreadPoolExecutor(max_workers=2) as pool:
            tasks = [pool.submit(worker, first, 123), pool.submit(worker, second, 124)]
            self.assertCountEqual([task.result(timeout=8) for task in tasks], [True, False])
        self.infer.assert_called_once()
        self.assertEqual(self.provider, {START_REF_PREFIX + self.inputs.semantic_key: HEAD})
        self.assertEqual([call.args[0] for call in self.request.call_args_list], ["POST", "POST", "GET"])

    def test_lost_provider_ack_is_unverified_and_blocks_a_fresh_coordinator(self):
        self.drop_ack = True
        first = self.registry("first.sqlite3")
        with serving(first, shared_budget=self.budget(123)) as port:
            with self.assertRaisesRegex(AttemptBlocked, "HTTP 503"):
                self.attempt(port, 123)
        self.request.assert_called_once()
        self.now = 121
        self.assertEqual(first.status(self.inputs)["state"], "UNVERIFIED")
        with serving(self.registry("second.sqlite3"), shared_budget=self.budget(124)) as port:
            with self.assertRaisesRegex(AttemptBlocked, "HTTP 409"):
                self.attempt(port, 124)
        self.infer.assert_not_called()

    def test_wrong_run_and_local_only_ack_do_not_spend_either_budget(self):
        for shared in (self.budget(123), None):
            with self.subTest(shared=shared is not None):
                registry = self.registry(f"mode-{shared is not None}.sqlite3")
                with serving(registry, shared_budget=shared) as port:
                    with self.assertRaisesRegex(AttemptBlocked, "HTTP 409"):
                        self.attempt(port, 124)
                self.assertEqual(registry.status(self.inputs)["state"], "LEASED")
        self.infer.assert_not_called()
        self.request.assert_not_called()

    def test_historical_ledger_budget_is_already_consumed(self):
        historical = w06.managed_attempt_input(ROOT, HEAD, self.build, MODEL)
        with self.assertRaisesRegex(AttemptBlocked, "historical ledger budget"):
            SharedBudget(historical, 123, self.request)
        self.request.assert_not_called()

    def test_head_drift_after_shared_acknowledgement_blocks_inference(self):
        with serving(self.registry("head.sqlite3"), shared_budget=self.budget(123)) as port, \
             patch.object(w06, "observed_head", side_effect=[HEAD, HEAD, PARENT]):
            with self.assertRaisesRegex(AttemptBlocked, "HEAD changed during admission"):
                self.attempt(port, 123)
        self.request.assert_called_once()
        self.infer.assert_not_called()

    def test_w06_cli_uses_shared_admission_before_stub_inference(self):
        metadata, lease_path, out = (self.root / name for name in ("metadata", "lease", "receipt"))
        metadata.write_text(json.dumps(MODEL), encoding="utf-8")
        with serving(self.registry("cli.sqlite3"), shared_budget=self.budget(123)) as port:
            client = RegistryClient(port, require_shared=True)
            lease = client.reserve(self.inputs, "coordinator", ttl_seconds=20)
            lease_path.write_text(json.dumps(asdict(lease)), encoding="utf-8")
            args = ["w06", "--head-sha", HEAD, "--run-id", "123", "--cli", "binary", "--gguf", "weights",
                    "--metadata", str(metadata), "--llama-revision", PARENT, "--out", str(out),
                    "--registry-port", str(port), "--lease", str(lease_path)]
            with patch.object(sys, "argv", args), patch.dict(w06.os.environ, {"GH_TOKEN": "", "GITHUB_TOKEN": ""}), \
                 patch.object(w06.p3g, "infer_prepared", self.infer), \
                 patch.object(w06.p3g, "sha256_file", return_value="b" * 64), redirect_stdout(StringIO()):
                self.assertEqual(w06.main(), 0)
        self.request.assert_called_once()
        self.infer.assert_called_once()
        self.assertFalse(json.loads(out.read_bytes())["merge_authorized"])


if __name__ == "__main__":
    unittest.main()
