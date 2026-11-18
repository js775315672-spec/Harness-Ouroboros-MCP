"""Record a completed W06 artifact only after checking its GitHub provenance."""
import hashlib

from p3l_w04_attempt_registry import AttemptBlocked
from p3l_w05_actions_source import github_api, read_model_archive


def reconcile(registry, inputs, lease, *, run_id, artifact_id, fetch=github_api):
    """Reconcile one delivery without dispatching a successor or invoking a model."""
    record = registry.status(inputs)
    if (record is None or record["state"] not in {"STARTED", "UNVERIFIED", "MODEL_GENERATED"}
            or type(run_id) is not int or run_id != record["run_id"]
            or inputs.task_key != record["task_key"] or lease.task_key != record["task_key"]
            or lease.owner != record["owner"] or lease.epoch != record["epoch"]):
        raise AttemptBlocked("completion event does not identify the admitted run")

    receipt, origin = read_model_archive(run_id, inputs.head_sha, artifact_id, fetch=fetch)
    raw = receipt.get("raw_response")
    if (receipt.get("schema") != "p3l-w06-one-shot-output-v1"
            or receipt.get("runner_role") != "model_inference"
            or type(receipt.get("run_id")) is not int or receipt["run_id"] != run_id
            or type(receipt.get("model_calls")) is not int or receipt["model_calls"] != 1
            or receipt.get("merge_authorized") is not False
            or origin.get("model_revision") != inputs.model_revision
            or origin.get("model_weights_sha256") != inputs.gguf_sha256
            or origin.get("inference_config_sha256") != inputs.inference_config_sha256
            or origin.get("prompt_sha256") != inputs.prompt_sha256
            or type(raw) is not str or not 1 <= len(raw.encode("utf-8")) <= 6000
            or hashlib.sha256(raw.encode("utf-8")).hexdigest() != receipt.get("raw_response_sha256")):
        raise AttemptBlocked("GitHub model artifact does not match the admitted inputs")

    registry.record_model_generated(lease, run_id=run_id,
                                    receipt_sha256=origin["model_archive_sha256"])
