"""Queue the first verified W08 proposal for W07 review without a model lease."""
import argparse
import hashlib
import json
from pathlib import Path

from p3l_w04_attempt_registry import AttemptInput, AttemptRegistry
from p3l_w02_model_handoff import SPEC
import p3l_w07_revision_isolation as w07
from task_selector import select


def historical_inputs(evidence):
    revision = w07.BASELINE_COMMIT
    verified, = w07.read_artifact(evidence, w07.VERIFIED_ARCHIVE, "verified.json")
    origin = verified["github_provenance"]
    parent = w07.git(w07.ROOT, "rev-parse", f"{revision}^").decode().strip()
    contract = w07.git(w07.ROOT, "show", f"{revision}:{SPEC.as_posix()}")
    return AttemptInput(
        task_type="ledger-validation",
        public_contract_sha256=hashlib.sha256(contract).hexdigest(),
        base_sha=parent,
        head_sha=revision,
        model_revision=origin["model_revision"],
        gguf_sha256=origin["model_weights_sha256"],
        inference_config_sha256=origin["inference_config_sha256"],
        prompt_sha256=origin["prompt_sha256"],
    )


def prepare_successor(registry, *, candidate, evidence):
    checked = w07.rehearse(candidate, evidence)
    previous = historical_inputs(evidence)
    choice = select()
    if (checked["status"] != "REVIEW_PENDING" or checked["historical_docker_test_count"] != 25
            or checked["w08_handoff_authorized"] is not False
            or choice["decision"] != "propose" or choice["coding_agent_connected"] is not False):
        raise ValueError("no review-only successor is eligible")
    proposal = {
        "schema": "p3l-w04-successor-proposal-v1",
        "status": "REVIEW_PENDING",
        "predecessor_task_key": previous.task_key,
        "w05_run_id": checked["w05_run_id"],
        "replay_archive_sha256": w07.REPLAY_ARCHIVE[1],
        "rehearsal_baseline_sha": checked["historical_commit"],
        "review_candidate_sha": checked["proposed_runtime_commit"],
        "phase": choice["phase"],
        "area": choice["area"],
        "task": choice["task"],
        "model_calls": 0,
        "w08_execution_authorized": False,
    }
    created = registry.queue_successor(previous, run_id=checked["w05_run_id"],
                                       receipt_sha256=w07.MODEL_ARCHIVE[1], proposal=proposal)
    return {"created": created, "proposal": proposal}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--candidate-checkout", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args()
    result = prepare_successor(AttemptRegistry(args.database), candidate=args.candidate_checkout,
                               evidence=args.evidence_root)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
