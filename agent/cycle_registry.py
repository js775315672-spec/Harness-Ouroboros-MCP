"""Repository-owned P0 cycle registry. Invoke from a GitHub Actions checkout."""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from urllib.request import Request, urlopen

AGENT = "ouroboros"
REMOTE = "https://github.com/js775315672-spec/Harness-Ouroboros-MCP.git"
REPOSITORY = REMOTE.removeprefix("https://github.com/").removesuffix(".git")
REF = "refs/heads/ofc-cycle-registry-v1"


class Blocked(Exception):
    pass


def git(*args, stdin=None):
    return subprocess.run(
        ["git", "-c", "user.name=OFC registry", "-c", "user.email=ofc@users.noreply.github.com", *args],
        input=None if stdin is None else stdin.encode("utf-8"), capture_output=True, check=True,
    ).stdout.decode("utf-8").strip()


def transition(state, command, owner, generation, source, value, now, ttl):
    if state and (state["agent"] != AGENT or state["schema"] != 1):
        raise Blocked("unexpected registry identity or schema")
    if command == "inspect":
        return state, False
    if not owner or not source:
        raise Blocked("owner and pinned source required")
    if command == "acquire":
        if ttl < 1 or ttl > 3600:
            raise Blocked("lease duration outside 1..3600 seconds")
        if state and state["phase"] != "complete":
            if state["source"] != source or state["phase"] == "blocked":
                raise Blocked("source drift or suspended cycle")
            if state["expires"] > now:
                raise Blocked("active lease")
            if state["pending"]:
                raise Blocked("unresolved external operation: " + state["pending"])
        else:
            state = dict(schema=1, agent=AGENT, cycle=uuid.uuid4().hex, source=source,
                         phase="open", generation=state.get("generation", 0), checkpoint=None, pending=None, results={key: receipt for key, receipt in state.get("results", {}).items()
                             if isinstance(receipt, dict) and receipt.get("kind") == "github_merge"})
        state.update(owner=owner, expires=now + ttl, generation=state["generation"] + 1)
        return state, True
    if not state or (owner, generation, source) != (state["owner"], state["generation"], state["source"]):
        raise Blocked("stale lease or source")
    if state["phase"] != "open" or state["expires"] <= now:
        raise Blocked("inactive lease")
    if command == "stop":
        state["phase"] = "blocked"
    elif command == "record":
        if state.get("merge_intent"):
            raise Blocked("merge receipt requires reconciliation")
        if not state["pending"] or not value:
            raise Blocked("pending operation and evidence required")
        key, separator, evidence = value.partition("=")
        if not separator or key != state["pending"] or not evidence:
            raise Blocked("operation key or evidence mismatch")
        state["results"][key] = evidence
        state["pending"] = None
    elif state["pending"]:
        raise Blocked("external outcome unresolved")
    elif command == "merge_intent":
        try:
            intent = json.loads(value)
        except ValueError as error:
            raise Blocked("invalid merge intent JSON") from error
        if not isinstance(intent, dict) or set(intent) != {"operation_key", "pr_number", "expected_head_sha"}:
            raise Blocked("invalid merge intent fields")
        key, number, head = (intent[k] for k in ("operation_key", "pr_number", "expected_head_sha"))
        if (not isinstance(key, str) or not key or "=" in key or key in state["results"]
                or type(number) is not int or number < 1 or not valid_sha(head)):
            raise Blocked("invalid or already recorded merge operation")
        intent.update(repository=REPOSITORY, base_sha=source, owner=owner,
                      generation=generation, cycle_id=state["cycle"])
        pr = github_pr(number)
        if pr.get("merged") is not False or pr.get("state") != "open":
            raise Blocked("expected an open, unmerged PR")
        validate_pr(pr, intent)
        state.update(pending=key, merge_intent=intent)
    elif command == "reserve":
        if not value or "=" in value or value in state["results"]:
            raise Blocked("invalid or previously executed operation")
        state["pending"] = value
    elif command == "checkpoint" and value:
        state["checkpoint"] = value
    elif command == "release":
        state["expires"] = 0
    elif command == "complete":
        state["phase"] = "complete"
    else:
        raise Blocked("invalid transition")
    return state, True


def valid_sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def github_pr(number):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise Blocked("authenticated GitHub API token required")
    request = Request(f"https://api.github.com/repos/{REPOSITORY}/pulls/{number}", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "User-Agent": "OFC-cycle-registry",
    })
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except (OSError, ValueError) as error:
        raise Blocked("GitHub PR evidence unavailable") from error


def validate_pr(pr, intent):
    try:
        base, head = pr["base"], pr["head"]
        matches = (pr["number"] == intent["pr_number"] and base["ref"] == "main"
                   and base["repo"]["full_name"] == intent["repository"]
                   and head["sha"] == intent["expected_head_sha"])
    except (KeyError, TypeError) as error:
        raise Blocked("GitHub PR evidence incomplete") from error
    if not matches:
        raise Blocked("PR repository, base branch or head mismatch")


def reconcile(remote, state, owner, generation, source, key, main, now):
    if state.get("agent") != AGENT or state.get("schema") != 1:
        raise Blocked("unexpected registry identity or schema")
    previous_receipt = state.get("results", {}).get(key)
    if isinstance(previous_receipt, dict) and previous_receipt.get("kind") == "github_merge":
        intent = previous_receipt["intent"]
        if (owner, generation, source, key) == tuple(intent[name] for name in
                ("owner", "generation", "base_sha", "operation_key")):
            return state, False
        raise Blocked("operation key already recorded")
    intent = state.get("merge_intent")
    if (not intent or state["pending"] != key or key != intent["operation_key"]
            or key in state["results"] or intent["repository"] != REPOSITORY
            or (owner, generation, source, state["cycle"]) != tuple(intent.get(field) for field in
                ("owner", "generation", "base_sha", "cycle_id"))
            or (owner, generation, source) != (state["owner"], state["generation"], state["source"])
            or state["phase"] != "open" or state["expires"] <= now):
        raise Blocked("merge intent or active lease mismatch")
    pr = github_pr(intent["pr_number"])
    validate_pr(pr, intent)
    merged = pr.get("merge_commit_sha")
    if pr.get("merged") is not True or not valid_sha(merged) or merged != main:
        raise Blocked("GitHub merge SHA must equal current main")
    git("fetch", "--no-write-fetch-head", "--quiet", "--no-tags", remote, merged)
    if git("show", "-s", "--format=%P", merged).split() != [source, intent["expected_head_sha"]]:
        raise Blocked("expected merge commit with pinned base and head parents")
    if state["expires"] <= time.time():
        raise Blocked("merge lease expired during verification")
    if git("ls-remote", remote, "refs/heads/main").split()[:1] != [merged]:
        raise Blocked("main changed during merge reconciliation")
    receipt = dict(kind="github_merge", intent=intent, main_before=source, main_after=merged,
                   pr_url=f"https://github.com/{REPOSITORY}/pull/{intent['pr_number']}")
    state["results"][key] = receipt
    state.update(pending=None, merge_intent=None, phase="complete", expires=0,
                 checkpoint=json.dumps(dict(merge_receipt=receipt, previous_checkpoint=state["checkpoint"])))
    return state, True


def transact(remote, command, owner="", generation=0, source="", value="", ttl=600):
    refs = git("ls-remote", remote, REF, "refs/heads/main")
    heads = dict(line.split()[::-1] for line in refs.splitlines())
    previous = heads.get(REF)
    state = {}
    if previous:
        git("fetch", "--no-write-fetch-head", "--quiet", "--no-tags", remote, previous)
        state = json.loads(git("show", previous + ":state.json"))
    if command not in ("inspect", "merge_reconcile") and heads.get("refs/heads/main") != source:
        raise Blocked("pinned main has changed")
    if command == "merge_reconcile":
        state, changed = reconcile(remote, state, owner, generation, source, value,
                                   heads.get("refs/heads/main"), time.time())
    else:
        state, changed = transition(state, command, owner, generation, source, value, time.time(), ttl)
    if changed:
        blob = git("hash-object", "-w", "--stdin", stdin=json.dumps(state, sort_keys=True) + "\n")
        tree = git("mktree", stdin=f"100644 blob {blob}\tstate.json\n")
        parents = ["-p", previous] if previous else []
        commit = git("commit-tree", tree, *parents, "-m", f"{AGENT} {command} {uuid.uuid4().hex}")
        try:
            git("push", "--porcelain", f"--force-with-lease={REF}:{previous or ''}", remote, commit + ":" + REF)
        except subprocess.CalledProcessError:
            if command != "merge_reconcile":
                raise
            current = transact(remote, "inspect")
            if current.get("results", {}).get(value) != state["results"][value]:
                raise Blocked("merge receipt CAS failed; registry reread, reconcile again only if intent remains")
            return current
    return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices="inspect acquire checkpoint reserve record release complete stop merge_intent merge_reconcile".split())
    parser.add_argument("--owner", default="")
    parser.add_argument("--generation", type=int, default=0)
    parser.add_argument("--source", default="")
    parser.add_argument("--value", default="")
    parser.add_argument("--ttl", type=int, default=600)
    try:
        print(json.dumps(transact(REMOTE, **vars(parser.parse_args())), sort_keys=True))
    except (Blocked, subprocess.CalledProcessError) as error:
        print("BLOCKED", error, file=sys.stderr)
        sys.exit(2)
