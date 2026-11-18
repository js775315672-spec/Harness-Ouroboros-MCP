"""Rehearse recovery of a synthetic W04 slot across Actions jobs."""
import argparse
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from threading import Thread

from p3l_w04_attempt_registry import AttemptBlocked, AttemptInput, AttemptRegistry, Lease, SHA256
from p3l_w04_local_service import RegistryClient, RegistryServer

START_TIME = 1_700_000_000
TTL = 30
MAX_SNAPSHOT = 256 * 1024


def snapshot_sha(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("missing or unsafe registry snapshot")
    with path.open("rb") as stream:
        data = stream.read(MAX_SNAPSHOT + 1)
    if not 1 <= len(data) <= MAX_SNAPSHOT:
        raise ValueError("invalid registry snapshot size")
    return hashlib.sha256(data).hexdigest()


def digest(label):
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def synthetic_inputs(base, head, run_id):
    if type(run_id) is not int or not 0 < run_id <= 2**63 - 1:
        raise ValueError("invalid rehearsal run id")
    return AttemptInput("runner-rehearsal", digest(f"rehearsal-contract:{run_id}"), base, head,
                        "0" * 40, digest("rehearsal-weights"), digest("rehearsal-config"),
                        digest("rehearsal-prompt"))


@contextmanager
def connected(path, now):
    with RegistryServer(AttemptRegistry(path, clock=lambda: now)) as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        try:
            yield RegistryClient(server.server_port)
        finally:
            server.shutdown()
            thread.join(timeout=5)


def publish(path, inputs, run_id):
    with path.open("xb"):
        pass
    with connected(path, START_TIME) as client:
        lease = client.reserve(inputs, "rehearsal-authority", ttl_seconds=TTL)
        client.start(lease, observed_head=inputs.head_sha, run_id=run_id)
    return {"snapshot_sha256": snapshot_sha(path), "simulated_start_count": 1}


def recover(path, inputs, run_id, expected_sha):
    if not SHA256.fullmatch(expected_sha) or snapshot_sha(path) != expected_sha:
        raise ValueError("registry snapshot digest mismatch")
    with connected(path, START_TIME + TTL + 1) as client:
        status = client.status(inputs)
        if (status is None or status["state"] != "UNVERIFIED" or status["run_id"] != run_id
                or status["task_key"] != inputs.task_key or status["expected_head"] != inputs.head_sha):
            raise ValueError("snapshot does not contain the expected spent slot")
        revised = replace(inputs, prompt_sha256=digest("revised-rehearsal-prompt"))
        try:
            client.reserve(revised, "rehearsal-retry", ttl_seconds=TTL)
        except AttemptBlocked as error:
            if str(error) != "registry did not admit request (HTTP 409)":
                raise
        else:
            raise RuntimeError("a spent slot admitted another reservation")
        old = Lease(status["task_key"], status["owner"], status["epoch"], status["expires_at"])
        try:
            client.start(old, observed_head=inputs.head_sha, run_id=run_id)
        except AttemptBlocked as error:
            if str(error) != "registry did not admit request (HTTP 409)":
                raise
        else:
            raise RuntimeError("a spent slot admitted another start")
    if snapshot_sha(path) != expected_sha:
        raise ValueError("a rejected retry changed the registry snapshot")
    return {"snapshot_sha256": expected_sha, "recovered_state": status["state"],
            "duplicate_reservation_blocked": True, "duplicate_start_blocked": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("publish", "recover"))
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    run_id = int(os.environ["GITHUB_RUN_ID"])
    inputs = synthetic_inputs(os.environ["REVIEW_BASE"], os.environ["REVIEW_HEAD"], run_id)
    if args.stage == "publish":
        result = publish(args.snapshot, inputs, run_id)
    else:
        result = recover(args.snapshot, inputs, run_id, os.environ["EXPECTED_SNAPSHOT_SHA"])
    result.update(stage=args.stage, run_id=run_id, task_key=inputs.task_key, model_calls=0,
                  review_head=inputs.head_sha, review_base=inputs.base_sha,
                  workflow_sha=os.environ["GITHUB_SHA"], runner=os.environ["RUNNER_NAME"])
    receipt = json.dumps(result, sort_keys=True) + "\n"
    args.receipt.write_text(receipt, encoding="utf-8")
    print(receipt, end="")


if __name__ == "__main__":
    main()
