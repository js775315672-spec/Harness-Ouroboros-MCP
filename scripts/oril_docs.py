"""Project public ORIL receipts into review-only documentation. Run from repo root."""
import argparse
from collections import defaultdict
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
from statistics import median
import subprocess
from urllib.request import Request, urlopen
import zipfile

REPO = "js775315672-spec/Harness-Ouroboros-MCP"
ROOT = "https://github.com/" + REPO
ARCHIVE = "bfa89dcc28287986e36e5d4f33693e53a8394902"
SEEDS = {44852655575: "957dcad940b875ced2ba3270f52014907d53a1f8",
         44853120822: "e8fa72cc4caecaf5afab952af5d5214baa9c2614"}
LEDGER = Path("docs/evolution/ledger.jsonl")
LESSONS = Path("docs/memory/lessons.jsonl")
TRENDS = Path("docs/metrics/trends.json")
STATUS = Path("docs/status/current.md")
ROADMAP = Path("docs/roadmap.md")
HYPOTHESES = ("remove_redundancy", "integer_format", "check_sum")
SCHEMA = "oril-doc-cycle-v1"
MARK = "<!-- oril-docs:generated -->"
CONDITION = ("base_sha", "model_revision", "workload_sha256", "grader_sha", "environment", "hypothesis")
METRICS = ("duration_seconds", "inference_seconds", "review_seconds", "success_rate",
           "regression_rate", "rollback_rate", "throughput_per_hour", "input_tokens",
           "rediscovery_seconds", "heldout_score", "public_score")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git(*args):
    return subprocess.check_output(["git", *args])


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def read_rows(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()] if path.exists() else []


def append(path, rows):
    if rows:
        prior = path.read_bytes() if path.exists() else b""
        with path.open("ab") as stream:
            if prior and not prior.endswith(b"\n"):
                stream.write(b"\n")
            for row in rows:
                stream.write((dump(row) + "\n").encode())


def api(path):
    headers = {"Accept": "application/vnd.github+json"}
    if os.getenv("GH_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    with urlopen(Request("https://api.github.com/repos/" + REPO + "/" + path,
                         headers=headers), timeout=30) as response:
        return json.load(response)


def elapsed(start, end):
    dt = datetime.fromisoformat
    value = (dt(end) - dt(start)).total_seconds()
    require(value >= 0, "invalid time interval")
    return value


def check_digest(data, expected, github_digest):
    actual = hashlib.sha256(data).hexdigest()
    require(actual == expected and github_digest == "sha256:" + actual, "artifact digest mismatch")
    return actual


def member(blob, name):
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        require(archive.namelist().count(name) == 1 and archive.getinfo(name).file_size < 2_000_000,
                "missing, repeated or oversized public member")
        return json.loads(archive.read(name))


def collect(source, run_id, live=False):
    path = f"docs/oril/evidence/{run_id}"
    run = api(f"actions/runs/{run_id}")
    jobs = api(f"actions/runs/{run_id}/attempts/1/jobs?per_page=100")["jobs"]
    artifacts = api(f"actions/runs/{run_id}/artifacts?per_page=100")["artifacts"]
    if live:
        # Only ingest a producer whose executable tree matches a reviewed reference.
        head = run["head_sha"]
        require(re.fullmatch("[0-9a-f]{40}", head), "invalid commit")
        git("fetch", "--no-tags", "origin", head)
        if git("diff", "--name-only", ARCHIVE, head, "--", ".", ":(exclude)**/*.md", ":(exclude)README.md").strip():
            return []
        manifest = {"head_sha": head, "run_id": run_id, "cycles": [{}, {}, {}],
                    "grader_sha": "f32dd7cc8b6e71995ae2c182ad6cc25c22ca0bdb"}
    else:
        manifest = json.loads(git("show", f"{source}:{path}/ledger.json"))
    head = manifest["head_sha"]
    require(re.fullmatch("[0-9a-f]{40}", head) and manifest["run_id"] == run_id, "invalid run identity")
    require(SEEDS.get(run_id, head) == head and run["head_sha"] == head and run["head_repository"]["full_name"] == REPO
            and run["path"] == ".github/workflows/oril-v3-integration.yml"
            and run["conclusion"] == "success" and run["run_attempt"] == 1, "unverified run")
    require(len(manifest["cycles"]) == 3, "incomplete campaign")
    result = []
    for i, cycle in enumerate(manifest["cycles"], 1):
        blobs = {}
        receipts = {}
        for kind, stage in (("raw", "infer"), ("review", "public-audit")):
            name = f"{kind}-{i}"
            job_name = ("first", "second", "third")[i-1] + " / " + stage
            if live:
                artifact, = [a for a in artifacts if a["name"] == name]
                job, = [j for j in jobs if j["name"] == job_name]
                require(artifact["size_in_bytes"] < 2_000_000, "oversized archive")
                data = subprocess.check_output(["gh", "api", f"repos/{REPO}/actions/artifacts/{artifact['id']}/zip"])
                ref = {"sha256": artifact["digest"].removeprefix("sha256:")}
            else:
                ref = cycle[kind]
                job, = [j for j in jobs if j["id"] == ref["job_id"]]
                artifact, = [a for a in artifacts if a["id"] == ref["artifact_id"]]
                data = git("show", f"{source}:{path}/{name}.zip")
            sha = check_digest(data, ref["sha256"], artifact["digest"])
            require(job["name"] == ("first", "second", "third")[i-1] + " / " + stage
                    and "ubuntu-24.04" in job["labels"] and job["conclusion"] == "success" and job["head_sha"] == head
                    and artifact["name"] == name, "unverified job or artifact")
            receipts[kind] = dict(sha256=sha, artifact_id=artifact["id"], job_id=job["id"],
                                  start=job["started_at"], end=job["completed_at"])
            blobs[kind] = data
        candidate = member(blobs["raw"], "candidate/candidate.json")
        ab = member(blobs["raw"], "candidate/ab.json")
        aa = member(blobs["raw"], "candidate/aa.json")
        audit = member(blobs["review"], "audit.json")["ab"]
        memory = member(blobs["review"], "memory.json")
        cycle_id = f"{run_id}-{i}"
        if live:
            base = candidate["base_sha"]
            require(re.fullmatch("[0-9a-f]{40}", base), "invalid baseline")
            git("cat-file", "-e", base + "^{commit}")
            manifest.setdefault("base_sha", base)
        require(candidate["implementation_sha"] == head and candidate["base_sha"] == manifest["base_sha"]
                and candidate["cycle_id"] == memory["cycle_id"] == cycle_id
                and candidate["hypothesis_id"] in HYPOTHESES
                and ab["model_id"] == "Qwen/Qwen2.5-0.5B-Instruct"
                and audit["raw_groups"] == len(ab["rows"]) == 30
                and memory["protected_grade"] == "pending", "invalid public provenance")
        matches = audit["public_exact_matches"]
        require(memory["candidate_errors"] == 30 - matches["compact"], "public score mismatch")
        raw, review = receipts["raw"], receipts["review"]
        observations = [o for report in (ab, aa) for row in report["rows"] for o in row["observations"]]
        require(len(observations) == 120, "incomplete calls")
        result.append(dict(schema=SCHEMA, cycle_id=cycle_id, run_id=run_id, candidate_sha=head,
                           base_sha=manifest["base_sha"], grader_sha=manifest["grader_sha"],
                           prompt_sha256=candidate["candidate_sha"], receipts=receipts,
                           hypothesis=candidate["hypothesis_id"], model=ab["model_id"],
                           model_revision=ab["resolved_revision"], workload_sha256=ab["public_tasks_sha256"],
                           environment="ubuntu-24.04-hosted-cpu", independent_review="public_replay",
                           improvement_verified=False, heldout_score=None, success_rate=None,
                           public_score=matches["compact"]/30, prior_correct=matches["verbose"],
                           regression_rate=(memory["regressions"]/matches["verbose"] if matches["verbose"] else None),
                           public_errors=memory["candidate_errors"], rollback_rate=None, rediscovery_seconds=None,
                           duration_seconds=elapsed(raw["start"], review["end"]),
                           inference_seconds=sum(o["elapsed_seconds"] for o in observations),
                           review_seconds=elapsed(review["start"], review["end"]),
                           throughput_per_hour=None, input_tokens=sum(o["input_tokens"] for o in observations),
                           next_action="independent_heldout_review"))
    return result


def validate(row):
    from jsonschema import Draft202012Validator
    Draft202012Validator(json.loads(Path("docs/memory/cycle.schema.json").read_bytes())).validate(row)
    require(all(0 <= n < float("inf") for n in (row["duration_seconds"], row["review_seconds"], row["inference_seconds"])), "invalid measurement")
    require(row["cycle_id"].split("-")[0] == str(row["run_id"]), "run mismatch")


def merge(rows, incoming):
    known = {r["cycle_id"]: r for r in rows}
    require(len(known) == len(rows), "duplicate ledger identity")
    additions = []
    for row in incoming:
        validate(row)
        key = row["cycle_id"]
        if key in known:
            require(row == known[key], "conflicting immutable cycle")
        else:
            known[key] = row
            additions.append(row)
    return additions


def trends(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in CONDITION)].append(row)
    reports = []
    for condition, group in sorted(groups.items()):
        sample = sorted(group, key=lambda r: r["receipts"]["review"]["end"])[-12:]
        measures = {}
        for key in METRICS:
            values = [r[key] for r in sample]
            current = delta = None
            if len(values) >= 5 and None not in values:
                current = median(values)
                split = len(values)//2
                before, after = median(values[:split]), median(values[-split:])
                if before:
                    delta = round(100*(after-before)/before, 4)
            higher_better = {"success_rate", "throughput_per_hour", "heldout_score", "public_score"}
            direction = "판단 불가"
            if delta is not None:
                direction = "동일" if delta == 0 else ("개선" if (delta > 0) == (key in higher_better) else "악화")
            measures[key] = {"median": current, "change_pct": delta, "observed_direction": direction}
        reports.append({"conditions": dict(zip(CONDITION, condition)), "cycles": [r["cycle_id"] for r in sample],
                        "metrics": measures})
    return reports


def section(path, content):
    original = path.read_text(encoding="utf-8")
    prefix = original.split(MARK)[0].rstrip()
    # README contains independently maintained DEV audit sections after the ORIL
    # generated summary. Preserve those sections on every documentation replay.
    suffix = ""
    if path == Path("README.md") and MARK in original:
        remainder = original.split(MARK, 1)[1]
        match = re.search(r"(?m)^## OFC DEV 12-cycle expansion", remainder)
        if match:
            suffix = "\n\n" + remainder[match.start():].rstrip("\n") + "\n"
    path.write_bytes((prefix + "\n\n" + MARK + "\n" + content + "\n" + suffix).encode())


def generate(incoming):
    rows = read_rows(LEDGER)
    additions = merge(rows, incoming)
    public = [r for r in rows + additions if r["schema"] == SCHEMA]
    for row in public:
        validate(row)
    public.sort(key=lambda r: (r["receipts"]["review"]["end"], r["cycle_id"]))
    reports = trends(public)
    lessons = read_rows(LESSONS)
    new_lessons = []
    for condition in sorted({tuple(r[k] for k in CONDITION) for r in public}):
        evidence = [r for r in public if tuple(r[k] for k in CONDITION) == condition and r["public_errors"]]
        hypothesis = condition[-1]
        ids = []
        runs = set()
        for record in evidence:
            ids.append(record["cycle_id"])
            runs.add(record["run_id"])
            if len(runs) < 2:
                continue
            lesson = dict(hypothesis=hypothesis, observation="residual_public_errors",
                          conditions=dict(zip(CONDITION, condition)), cycles=ids.copy(),
                          next_action="independent_heldout_review")
            if lesson not in lessons:
                new_lessons.append(lesson)
    append(LEDGER, additions)
    append(LESSONS, new_lessons)
    TRENDS.write_bytes((json.dumps(reports, ensure_ascii=False, indent=2, sort_keys=True)+"\n").encode())
    summary = "새 공개 검산 기록 없음."
    if public:
        last = public[-1]
        summary = (f"최근 공개 검산 [{last['cycle_id']}]({ROOT}/actions/runs/{last['run_id']}) · "
                   f"코드 `{last['candidate_sha']}` · 공개 오답 {last['public_errors']}/30 · "
                   f"소요 {last['duration_seconds']:g}초. 비공개 개선 미입증.")
    if reports:
        latest_group = next(g for g in reports if public[-1]["cycle_id"] in g["cycles"])
        duration = latest_group["metrics"]["duration_seconds"]
        summary += (f" 동일 조건 {len(latest_group['cycles'])}건, 소요 시간 변화 {duration['observed_direction']}."
                    + (f" 중앙값 {duration['median']:g}초 ({duration['change_pct']:+g}%)."
                       if duration["change_pct"] is not None else ""))
    section(Path("README.md"), summary + "\n\n[자동 집계](docs/metrics/trends.json) · [로드맵](docs/roadmap.md)")
    status = summary
    snapshot = Path("docs/status/github.json")
    if os.getenv("ORIL_DISCOVER") == "1":
        pr = api("pulls/330")
        require(re.fullmatch("[0-9a-f]{40}", pr["head"]["sha"]), "invalid PR head")
        checks = []
        for name in ("oril-private-baseline.yml", "oril-runner-qualification.yml", "hydra-standing.yml"):
            runs = api(f"actions/workflows/{name}/runs?branch=main&status=completed&per_page=1")["workflow_runs"]
            if runs:
                run = runs[0]
                require(re.fullmatch("[0-9a-f]{40}", run["head_sha"]) and type(run["id"]) is int
                        and run["conclusion"] in {"success","failure","cancelled","timed_out","neutral","skipped",
                                                  "stale","action_required","startup_failure"}, "invalid run status")
                checks.append(dict(workflow=name, sha=run["head_sha"], run_id=run["id"], conclusion=run["conclusion"]))
        state = "merged" if pr["merged"] else ("draft" if pr["draft"] and pr["state"]=="open" else pr["state"])
        require(state in {"open","closed","draft","merged"}, "unknown PR state")
        pulls = []
        page = 1
        while True:
            batch = api(f"pulls?state=open&base=main&per_page=100&page={page}")
            for item in batch:
                if item["head"]["ref"] != "docs/oril-generated":
                    require(type(item["number"]) is int and re.fullmatch("[0-9a-f]{40}", item["head"]["sha"]),
                            "invalid PR identity")
                    pulls.append(dict(number=item["number"], sha=item["head"]["sha"], draft=item["draft"]))
            if len(batch) < 100:
                break
            page += 1
        snapshot.write_bytes((dump(dict(pr330=state, sha=pr["head"]["sha"], checks=checks, pending=pulls))+"\n").encode())
    if snapshot.exists():
        snap = json.loads(snapshot.read_bytes())
        status += f"\n\nmain 대상 검토 대기 {len(snap['pending'])}건. [PR별 SHA](github.json)"
        status += f"\n\n[#330]({ROOT}/pull/330) · {snap['pr330']} · `{snap['sha']}`"
        for check in snap["checks"]:
            status += f"\n\n[{check['workflow']}]({ROOT}/actions/runs/{check['run_id']}) · {check['conclusion']} · `{check['sha']}`"
    section(STATUS, status + "\n\n[비교 조건·측정값](../metrics/trends.json) · [근거별 교훈](../memory/lessons.jsonl)")
    ROADMAP.write_text("# 검토용 로드맵\n\n공개 검산 " + str(len(public)) +
                       "건. 다음 단계는 고정된 비공개 평가와 독립 승인이다.\n", encoding="utf-8")


def context():
    baseline = json.loads(Path("docs/evolution/cycle-01-dispatch-preflight.json").read_bytes())
    cycles = [r for r in read_rows(LEDGER) if r["schema"] == SCHEMA]
    for row in cycles:
        validate(row)
    return {"sha": git("rev-parse", "HEAD").decode().strip(), "rules": Path("AGENTS.md").read_text(encoding="utf-8"),
            "architecture": Path("docs/architecture.md").read_text(encoding="utf-8"),
            "baseline": baseline["base_commit"], "gate": baseline["status"], "next_gate": baseline["required_next_evidence"],
            "lessons": read_rows(LESSONS)[-12:], "recent_cycles": sorted(
                cycles,
                key=lambda r: r["receipts"]["review"]["end"])[-5:]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["sync", "context", "render"])
    mode = parser.parse_args().mode
    if mode == "context":
        print(dump(context()))
        return
    incoming = []
    if mode == "sync":
        sources = {r: ARCHIVE for r in SEEDS}
        for manifest in Path("docs/oril/evidence").glob("*/ledger.json"):
            sources[int(manifest.parent.name)] = "HEAD"
        for run, source in sorted(sources.items()):
            incoming.extend(collect(source, run))
        if os.getenv("ORIL_DISCOVER") == "1":
            existing = {r["run_id"] for r in read_rows(LEDGER) if r["schema"] == SCHEMA}
            page = 1
            while True:
                runs = api(f"actions/runs?branch=integration/oril-v3-public-loop&per_page=100&page={page}")["workflow_runs"]
                for run in runs:
                    if (run["id"] not in existing | sources.keys() and run["id"] > max(SEEDS)
                            and run["path"] == ".github/workflows/oril-v3-integration.yml"
                            and run["conclusion"] == "success" and run["run_attempt"] == 1
                            and run["head_repository"] and run["head_repository"]["full_name"] == REPO):
                        jobs = api(f"actions/runs/{run['id']}/jobs?per_page=100")["jobs"]
                        if any(j["name"] == "third / public-audit" and j["conclusion"] == "success" for j in jobs):
                            incoming.extend(collect(None, run["id"], live=True))
                if len(runs) < 100:
                    break
                page += 1
    generate(incoming)


if __name__ == "__main__":
    main()
