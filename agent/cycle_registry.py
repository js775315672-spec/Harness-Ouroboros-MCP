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
        input=stdin.encode("utf-8") if stdin is not None else None, capture_output=True, check=True,
    ).stdout.decode("utf-8").strip()


def transition(state, command, owner, generation, source, value, now, ttl):
    if state and (state["agent"] != AGENT or state["schema"] != 1):
        raise Blocked("unexpected registry identity or schema")
    if command == "inspect":
        return state, False
    if not owner or not source:
        raise Blocked("owner and pinned source required")
    if command == "recover":
        # A recovery is not an acquire: the caller must prove the observed generation.
        # Never silently resolve a pending external side effect.
        if not state or state["phase"] != "open":
            raise Blocked("no recoverable open cycle")
        if generation != state["generation"]:
            raise Blocked("stale recovery generation")
        if source != state["source"]:
            raise Blocked("source drift during recovery")
        if state["expires"] > now:
            raise Blocked("lease has not expired")
        if state["pending"]:
            raise Blocked("unresolved external operation: " + state["pending"])
        if ttl < 1 or ttl > 3600:
            raise Blocked("lease duration outside 1..3600 seconds")
        state.update(owner=owner, expires=now + ttl,
                     generation=state["generation"] + 1)
        return state, True
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
        git("fetch", "--quiet", "--no-tags", remote, f"+{REF}:refs/remotes/ofc-registry-cache")
        try:
            state = json.loads(git("show", "refs/remotes/ofc-registry-cache:state.json"))
        except subprocess.CalledProcessError as exc:
            raise Blocked("registry read failed: " + (exc.stderr or str(exc))) from exc
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices="inspect acquire recover checkpoint reserve record release complete stop".split())
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
