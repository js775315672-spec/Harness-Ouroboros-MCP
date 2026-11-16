"""Bounded verifier-guided repair loop with sanitized error feedback.

Current behavior rejects invalid answers and retries with an identical prompt at
temperature 0, which tends to reproduce the same wrong answer. This loop (a) feeds the
verifier's structured failure back into the next prompt, (b) escalates temperature and
seed only after a greedy failure, (c) never re-verifies a duplicate response, and
(d) stays within a hard call budget. The generator and verifier are injected, so the
existing AST gate and Docker controls remain the only authority on acceptance.
"""
import hashlib
import re
from dataclasses import dataclass, field

_CONTROL = re.compile(r"[^\x20-\x7e\n]")


@dataclass(frozen=True)
class Verdict:
    ok: bool
    stage: str = ""      # e.g. "ast_gate", "baseline_negative", "candidate_positive"
    detail: str = ""


@dataclass
class Attempt:
    index: int
    temperature: float
    seed: int
    response: str
    duplicate: bool
    verdict: Verdict


@dataclass
class RepairResult:
    passed: bool
    attempts: list = field(default_factory=list)

    @property
    def model_calls(self):
        return len(self.attempts)


def sanitize_feedback(text, limit=300):
    """Untrusted tool output -> short printable-ASCII hint (no control bytes)."""
    cleaned = _CONTROL.sub("?", str(text))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:limit]


def build_retry_prompt(base_prompt, previous, limit=300):
    hint = sanitize_feedback(previous.verdict.detail, limit)
    note = ("\n\nYour previous answer was rejected at stage '%s': %s\n"
            "Answer again with one corrected expression only." %
            (sanitize_feedback(previous.verdict.stage, 40), hint))
    if previous.duplicate:
        note += " Do not repeat the previous answer."
    return base_prompt + note


DEFAULT_SCHEDULE = ((0.0, 0), (0.4, 11), (0.7, 23))  # (temperature, seed)


def run_bounded_repair(generate, verify, base_prompt, schedule=DEFAULT_SCHEDULE):
    """generate(prompt, temperature=, seed=) -> str; verify(str) -> Verdict."""
    if not 1 <= len(schedule) <= 5:
        raise ValueError("call budget must be between 1 and 5")
    result = RepairResult(passed=False)
    seen = set()
    prompt = base_prompt
    for index, (temperature, seed) in enumerate(schedule):
        response = generate(prompt, temperature=temperature, seed=seed)
        digest = hashlib.sha256(response.encode("utf-8", "replace")).hexdigest()
        duplicate = digest in seen
        seen.add(digest)
        if duplicate:
            verdict = Verdict(False, "duplicate", "identical to an earlier answer")
        else:
            verdict = verify(response)
        attempt = Attempt(index, temperature, seed, response, duplicate, verdict)
        result.attempts.append(attempt)
        if verdict.ok:
            result.passed = True
            break
        prompt = build_retry_prompt(base_prompt, attempt)
    return result
