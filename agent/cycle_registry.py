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
        git("fetch", "--no-write-fetch-head", "--quiet", "--no-tags", remote, previous)
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


def recover_verified(remote, *, owner, source, operation, evidence, verifier, ttl=600):
    """CAS recovery; trusted verifier must authenticate repo, PR, and merge evidence."""
    refs = git("ls-remote", remote, REF, "refs/heads/main")
    heads = dict(line.split()[::-1] for line in refs.splitlines())
    previous = heads.get(REF)
    if not previous or heads.get("refs/heads/main") != source:
        raise Blocked("missing registry or pinned main changed")
    git("fetch", "--no-write-fetch-head", "--quiet", "--no-tags", remote, previous)
    state = json.loads(git("show", previous + ":state.json"))
    if not callable(verifier) or verifier(remote, operation, evidence) is not True:
        raise Blocked("external outcome not authenticated")
    result = reconcile_expired(state, owner=owner, source=source, operation=operation,
                               evidence=evidence, verified=True, now=time.time(), ttl=ttl)
    blob = git("hash-object", "-w", "--stdin", stdin=json.dumps(result, sort_keys=True) + "\n")
    tree = git("mktree", stdin=f"100644 blob {blob}\tstate.json\n")
    commit = git("commit-tree", tree, "-p", previous, "-m", f"{AGENT} reconcile {uuid.uuid4().hex}")
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
