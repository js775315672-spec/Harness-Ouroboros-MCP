import hashlib
import json
import os
import urllib.request

from cycle_registry import AGENT, REMOTE, Blocked, git, transact
from public_cycle_probe import evaluate


def request(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/" + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.load(response)


def main():
    count = int(os.environ["COUNT"])
    start = {1: 0, 3: 1, 6: 4, 9: 10}[count]
    run = os.environ["GITHUB_RUN_ID"]
    source = os.environ["SOURCE"]
    target = git("-C", "target", "rev-parse", "HEAD")
    owner = "/".join([run, os.environ["GITHUB_RUN_ATTEMPT"], str(count)])
    state = transact(REMOTE, "inspect")
    prior = json.loads(state["checkpoint"])
    model = "qwen2.5:0.5b"
    digest = next(m["digest"] for m in request("tags")["models"] if m["name"] == model)
    if count == 1:
        if state["phase"] != "open" or prior.get("target_sha") != target or "batch_run" in prior:
            raise Blocked("expected released first research checkpoint")
    elif state["phase"] != "complete" or prior.get("batch_run") != run or prior.get("index") != start-1:
        raise Blocked("preceding batch incomplete")
    memory = prior.get("memory", {})
    for index in range(start, start + count):
        lease = transact(REMOTE, "acquire", owner, source=source, ttl=600)
        args = owner, lease["generation"], source
        if index == 0 and lease["cycle"] != state["cycle"]:
            raise Blocked("initial cycle changed")
        if index and (lease["checkpoint"] or lease["generation"] != state["generation"] + 1):
            raise Blocked("intervening writer")
        goal, examples, expected, choices, default = evaluate(AGENT, index, lease["cycle"])
        previous = memory.get(goal, default)
        prompt = json.dumps(dict(goal=goal, public_examples=examples, action_choices=list(choices),
                                 previous_strategy=previous, previous_result=prior.get("score"),
                                 instruction="Choose one listed action for this goal. Return the action field."))
        transact(REMOTE, "reserve", *args, value="qwen-public-trial")
        answer = request("generate", dict(model=model, prompt=prompt, stream=False,
                         format={"type":"object","properties":{"action":{"type":"string","enum":list(choices)}},
                                 "required":["action"]}, options=dict(temperature=0, num_predict=64, num_ctx=2048)))
        raw = answer["response"]
        try:
            candidate = json.loads(raw)["action"]
        except (ValueError, KeyError, TypeError):
            candidate = None
        valid = isinstance(candidate, str) and candidate in choices
        score = lambda key: sum(a == b for a,b in zip(choices[key], expected))
        baseline = score(previous)
        result = score(candidate) if valid else None
        if valid and result > baseline:
            memory[goal] = candidate
        public = "invalid_output" if not valid else "improved" if result > baseline else "regressed" if result < baseline else "tied"
        report = dict(batch_run=run, index=index, batch_size=count, target_sha=target, main_sha=source,
                      workflow_sha=os.environ["GITHUB_SHA"], cycle=lease["cycle"], goal=goal,
                      model=model, model_digest=digest, prompt=prompt, response=raw, 
                      examples=examples, expected=expected, measured_choices=choices,
                      baseline_action=previous, candidate=candidate, baseline_score=baseline, score=result,
                      denominator=len(expected), public_result=public, memory=memory,
                      gain="INCONCLUSIVE", protected_evaluation=False,
                      prompt_tokens=answer.get("prompt_eval_count"), generated_tokens=answer.get("eval_count"))
        evidence = json.dumps(report, sort_keys=True, ensure_ascii=False)
        transact(REMOTE, "record", *args, value="qwen-public-trial="+hashlib.sha256(evidence.encode()).hexdigest())
        transact(REMOTE, "checkpoint", *args, value=evidence)
        state = transact(REMOTE, "complete", *args)
        print(index+1, lease["cycle"], public, baseline, result, flush=True)
        prior = report


if __name__ == "__main__":
    main()
