"""Repository-owned P0 cycle registry. Invoke from a GitHub Actions checkout."""
import argparse
import json
import subprocess
import sys
import time
import uuid

AGENT = "ouroboros"
REMOTE = "https://github.com/js775315672-spec/Harness-Ouroboros-MCP.git"
REF = "refs/heads/ofc-cycle-registry-v1"


class Blocked(Exception):
    pass


def git(*args, stdin=None):
    return subprocess.run(
        ["git", "-c", "user.name=OFC registry", "-c", "user.email=ofc@users.noreply.github.com", *args],
        input=stdin, text=True, capture_output=True, check=True,
    ).stdout.strip()


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
                         phase="open", generation=state.get("generation", 0), checkpoint=None, pending=None, results={})
        state.update(owner=owner, expires=now + ttl, generation=state["generation"] + 1)
        return state, True
    if not state or (owner, generation, source) != (state["owner"], state["generation"], state["source"]):
        raise Blocked("stale lease or source")
    if state["phase"] != "open" or state["expires"] <= now:
        raise Blocked("inactive lease")
    if command == "stop":
        state["phase"] = "blocked"
    elif command == "record":
        if state["pending"] and state["pending"].lstrip().startswith("{"):
            raise Blocked("merge operations require authenticated recovery, not generic record")
        if not state["pending"] or not value:
            raise Blocked("pending operation and evidence required")
        key, separator, evidence = value.partition("=")
        if not separator or key != state["pending"] or not evidence:
            raise Blocked("operation key or evidence mismatch")
        state["results"][key] = evidence
        state["pending"] = None
    elif state["pending"]:
        raise Blocked("external outcome unresolved")
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


def transact(remote, command, owner="", generation=0, source="", value="", ttl=600):
    refs = git("ls-remote", remote, REF, "refs/heads/main")
    heads = dict(line.split()[::-1] for line in refs.splitlines())
    previous = heads.get(REF)
    state = {}
    if previous:
        git("fetch", "--quiet", "--no-tags", remote, REF)
        state = json.loads(git("show", previous + ":state.json"))
    if command != "inspect" and heads.get("refs/heads/main") != source:
        raise Blocked("pinned main has changed")
    state, changed = transition(state, command, owner, generation, source, value, time.time(), ttl)
    if changed:
        blob = git("hash-object", "-w", "--stdin", stdin=json.dumps(state, sort_keys=True) + "\n")
        tree = git("mktree", stdin=f"100644 blob {blob}\tstate.json\n")
        parents = ["-p", previous] if previous else []
        commit = git("commit-tree", tree, *parents, "-m", f"{AGENT} {command} {uuid.uuid4().hex}")
        git("push", "--porcelain", f"--force-with-lease={REF}:{previous or ''}", remote, commit + ":" + REF)
    return state


def reconcile_expired(state, *, owner, source, operation, evidence, verified, now, ttl=600):
    """Reconcile an expired pending operation only after trusted external verification."""
    if not state or state.get("schema") != 1 or state.get("agent") != AGENT:
        raise Blocked("registry identity mismatch")
    if state.get("phase") != "open" or not state.get("pending"):
        raise Blocked("no recoverable pending operation")
    if state.get("expires", 0) > now:
        raise Blocked("existing lease still active")
    if state.get("source") != source or not owner or not operation or operation != state["pending"]:
        raise Blocked("recovery identity or operation mismatch")
    if verified is not True or not isinstance(evidence, str) or not evidence.strip():
        raise Blocked("independent authenticated outcome required")
    if not 1 <= ttl <= 3600 or operation in state.get("results", {}):
        raise Blocked("invalid recovery lease or duplicate operation")
    recovered = dict(state)
    recovered["results"] = dict(state["results"])
    recovered["results"][operation] = evidence
    recovered["pending"] = None
    recovered["owner"] = owner
    recovered["generation"] = state["generation"] + 1
    recovered["expires"] = now + ttl
    return recovered


def recover_verified(*args, **kwargs):
    """Legacy verifier injection is unsafe and permanently disabled."""
    raise Blocked("arbitrary verifier callback forbidden; use recover_merged_pr")



def verify_github_merge(remote, operation, evidence, *, api_fetch=None):
    """Fail-closed verification of a pinned PR merge receipt against GitHub API.

    operation/evidence are canonical JSON strings. This is a verifier primitive,
    not an authorization to merge or mutate a live registry.
    """
    import re
    from urllib.parse import quote
    from urllib.request import Request, urlopen
    if remote != REMOTE:
        raise Blocked("repository remote mismatch")
    try:
        intent = json.loads(operation)
        receipt = json.loads(evidence)
    except (TypeError, ValueError) as exc:
        raise Blocked("invalid merge intent or receipt JSON") from exc
    if not isinstance(intent, dict) or not isinstance(receipt, dict):
        raise Blocked("merge evidence must be objects")
    repo = REMOTE.removeprefix("https://github.com/").removesuffix(".git")
    sha = re.compile(r"^[0-9a-f]{40}$")
    if (intent.get("repository") != repo or receipt.get("repository") != repo
            or not isinstance(intent.get("pr"), int) or isinstance(intent.get("pr"), bool)
            or intent["pr"] < 1 or receipt.get("pr") != intent["pr"]
            or not isinstance(intent.get("operation_id"), str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{8,128}", intent["operation_id"])
            or receipt.get("operation_id") != intent["operation_id"]):
        raise Blocked("repository, PR or operation identity mismatch")
    for field in ("head_sha", "base_sha"):
        if (not isinstance(intent.get(field), str) or not sha.fullmatch(intent[field])
                or receipt.get(field) != intent[field]):
            raise Blocked("pinned head/base SHA mismatch")
    merge_sha = receipt.get("merge_commit_sha")
    if not isinstance(merge_sha, str) or not sha.fullmatch(merge_sha):
        raise Blocked("invalid merge commit SHA")
    url = f"https://api.github.com/repos/{repo}/pulls/{intent['pr']}"
    if api_fetch is None:
        def api_fetch(target):
            request = Request(target, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "ofc-registry-verifier"})
            with urlopen(request, timeout=10) as response:
                return json.load(response)
    try:
        data = api_fetch(url)
    except Exception as exc:
        raise Blocked("GitHub merge status unavailable") from exc
    if not isinstance(data, dict):
        raise Blocked("invalid GitHub response")
    if data.get("number") not in (None, intent["pr"]):
        raise Blocked("GitHub PR number mismatch")
    if (data.get("merged") is not True or data.get("state") != "closed"
            or data.get("merge_commit_sha") != merge_sha
            or not isinstance(data.get("head"), dict)
            or not isinstance(data.get("base"), dict)
            or data["head"].get("sha") != intent["head_sha"]
            or data["base"].get("sha") != intent["base_sha"]
            or not isinstance(data.get("base", {}).get("repo"), dict)
            or data["base"]["repo"].get("full_name") != repo):
        raise Blocked("unconfirmed or changed GitHub merge")
    return True



def recover_merged_pr(remote, *, owner, source, operation, evidence, ttl=600, api_fetch=None):
    """Recover only a confirmed merge whose commit is the current main tip.

    No caller-supplied verification boolean is accepted. Registry CAS remains
    mandatory; uncertainty and later main changes are deliberately blocked.
    """
    if remote != REMOTE:
        raise Blocked("recovery remote is not this agent's repository")
    try:
        intent, receipt = json.loads(operation), json.loads(evidence)
    except (TypeError, ValueError) as exc:
        raise Blocked("invalid merge evidence") from exc
    if not isinstance(intent, dict) or not isinstance(receipt, dict):
        raise Blocked("invalid merge evidence objects")
    if intent.get("base_sha") != source:
        raise Blocked("merge intent does not match pinned source")
    refs = git("ls-remote", remote, REF, "refs/heads/main")
    heads = dict(line.split()[::-1] for line in refs.splitlines())
    previous, current_main = heads.get(REF), heads.get("refs/heads/main")
    if not previous or not current_main or current_main != receipt.get("merge_commit_sha"):
        raise Blocked("main is not the authenticated merge commit")
    git("fetch", "--no-write-fetch-head", "--quiet", "--no-tags", remote, previous)
    state = json.loads(git("show", previous + ":state.json"))
    if state.get("source") != source or state.get("pending") != operation:
        raise Blocked("pending operation or registry source mismatch")
    if state.get("phase") != "open" or not isinstance(state.get("results"), dict):
        raise Blocked("malformed registry state")
    if verify_github_merge(remote, operation, evidence, api_fetch=api_fetch) is not True:
        raise Blocked("merge receipt verification failed")
    result = reconcile_expired(state, owner=owner, source=source, operation=operation,
                               evidence=evidence, verified=True, now=time.time(), ttl=ttl)
    blob = git("hash-object", "-w", "--stdin", stdin=json.dumps(result, sort_keys=True) + "\n")
    tree = git("mktree", stdin=f"100644 blob {blob}\tstate.json\n")
    commit = git("commit-tree", tree, "-p", previous, "-m", f"{AGENT} authenticated merge recovery {uuid.uuid4().hex}")
    git("push", "--porcelain", f"--force-with-lease={REF}:{previous}", remote, commit + ":" + REF)
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices="inspect acquire checkpoint reserve record release complete stop".split())
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
