"""Evaluate provenance independently of any candidate-supplied result files."""
from hashlib import sha256
from .contracts import Candidate, EvidenceRecord, ExperimentSpec

class Evaluator:
    def validate(self, spec: ExperimentSpec, candidate: Candidate, record: EvidenceRecord) -> bool:
        return (
            candidate.experiment_id == spec.experiment_id == record.experiment_id
            and candidate.candidate_sha == record.candidate_sha
            and record.agent_id == spec.agent_id
            and record.evaluation_manifest_sha256 == spec.evaluation_manifest_sha256
            and record.evaluator_id != spec.agent_id.value
            and record.independence_attestation
        )

    @staticmethod
    def check_artifact(record: EvidenceRecord, artifact: bytes) -> bool:
        return sha256(artifact).hexdigest() == record.artifact_sha256
