"""Recompute public metrics using a separate, pinned checkout of the auditors."""
import hashlib
import json
import os
from pathlib import Path
import sys

from oril_v2_slot2_public30_independent_audit import audit as audit_ab, read_unique
from oril_v2_slot4_public30_aa_independent_audit import audit as audit_aa


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    folder = Path("candidate")
    candidate = read_unique(folder / "candidate.json")
    run = os.environ["GITHUB_RUN_ID"]
    n = int(os.environ["CYCLE"])
    if candidate["cycle_id"] != f"{run}-{n}" or candidate["implementation_sha"] != os.environ["SOURCE_SHA"]:
        raise ValueError("candidate identity mismatch")
    previous = Path("input/memory.json" if n>1 else "input/public_30_pairs.json")
    if digest(previous) != candidate["parent_evidence_sha256"]:
        raise ValueError("parent digest mismatch")
    if candidate["candidate_sha"] != hashlib.sha256(candidate["prompt"].encode()).hexdigest():
        raise ValueError("prompt digest mismatch")
    results = {}
    for name, audit in [("ab", audit_ab), ("aa", audit_aa)]:
        path = folder / f"{name}.json"
        if digest(path) != candidate["raw_sha256"][path.name]:
            raise ValueError("raw digest mismatch")
        raw = read_unique(path)
        if raw["resolved_revision"] != "7ae557604adf67be50417f59c2c2f167def9a775" or raw["weight_files"][0]["sha256"] != "fdf756fa7fcbe7404d5c60e26bff1a0c8b8aa1f72ced49e7dd0210fe288fb7fe":
            raise ValueError("unexpected model")
        results[name] = audit(raw)
    ab = results["ab"]
    regressions = ab["paired_accuracy_discordance"]["verbose_only_correct"]
    savings = ab["token_saving_pct_descriptive"]
    memory = dict(cycle_id=candidate["cycle_id"], tried=candidate["tried"],
                  candidate_errors=30-ab["public_exact_matches"]["compact"],
                  regressions=regressions, evidence_sha256=digest(folder/"candidate.json"),
                  state="rejected" if regressions or savings<20 else "tested",
                  protected_grade="pending", promotion_allowed=False)
    Path("memory.json").write_text(json.dumps(memory, sort_keys=True)+"\n", encoding="utf-8")
    Path("audit.json").write_text(json.dumps(results,sort_keys=True)+"\n", encoding="utf-8")
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as f:
        print(f"### 공개 사이클 {candidate['cycle_id']}\n", file=f)
        print(f"기준 {candidate['base_sha']} · 후보 {candidate['candidate_sha']} · 원시 증거 {candidate['raw_sha256']}\n", file=f)
        print(f"정확 일치 {ab['public_exact_matches']} / 30 · 입력 토큰 {ab['input_tokens']} · 호출 지연 중앙값(초) {ab['latency_median_seconds']} · 신규 회귀 {regressions}건\n", file=f)
        print(f"검산은 고정된 별도 체크아웃에서 실행. 가설 {candidate['hypothesis_id']} · 상태 {memory['state']} · 다음 주기에 시도 목록과 오류 수 인계. 비공개 평가·금전 비용·5회 이상 추세 미측정.", file=f)


if __name__ == "__main__":
    main()
