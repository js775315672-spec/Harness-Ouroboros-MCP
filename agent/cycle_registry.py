"""Repository-owned P0 cycle registry. Invoke from a GitHub Actions checkout."""
import argparse
import json
import hashlib
import re
import os
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
    # Send raw UTF-8 bytes: text=True translates LF to CRLF on Windows,
    # which can make mktree create a file named "state.json\\r".
    data = stdin.encode("utf-8") if isinstance(stdin, str) else stdin
    result = subprocess.run(
        ["git", "-c", "user.name=OFC registry", "-c", "user.email=ofc@users.noreply.github.com", *args],
        input=data, capture_output=True, check=True,
    )
    return result.stdout.decode("utf-8").strip()



def assert_canonical_registry_tree(remote, commit):
    """Never interpret an anomalous live Git tree as a trusted registry state.

    Historical state.json + CR remains observable by the read-only history
    auditor, but cannot be the *active* registry ref used for a transition.
    """
    prefix = ["--git-dir=" + remote] if os.path.isdir(remote) else []
    entries = git(*prefix, "ls-tree", "--name-only", commit).splitlines()
    if entries != ["state.json"]:
        raise Blocked("noncanonical active registry tree; manual review required: " +
                      repr(entries))




R1_PROTOCOL = "OFC-R1"
R1_RECEIPT = "OFC-R1-RECEIPT"
R1_ID = re.compile(r"^[A-Za-z0-9_.:/-]{8,160}$")


def r1_ledger(state):
    """Only forward-written R1 tombstones are authoritative; legacy history is not."""
    guard = state.get("r1_guard")
    if guard is None:
        guard = {"operations": {}, "effects": {}, "receipts": {}}
    if (not isinstance(guard, dict) or set(guard) !=
            {"operations", "effects", "receipts"} or
            any(not isinstance(guard[k], dict) for k in guard)):
        raise Blocked("malformed global idempotency guard")
    return guard


def r1_intent(raw, state):
    """Return None for legacy/merge JSON, and validate explicitly opted-in R1."""
    if not isinstance(raw, str) or not raw.lstrip().startswith("{"):
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("protocol") != R1_PROTOCOL:
        if isinstance(data, dict) and data.get("protocol") is not None:
            raise Blocked("unsupported external-operation protocol")
        return None
    required = {"protocol", "agent", "cycle_id", "operation_id", "effect_id", "source"}
    if (set(data) != required or data["agent"] != AGENT or
            data["cycle_id"] != state["cycle"] or data["source"] != state["source"] or
            any(not isinstance(data[k], str) or not R1_ID.fullmatch(data[k])
                for k in ("operation_id", "effect_id"))):
        raise Blocked("R1 cycle, operation, effect or source identity mismatch")
    return data


def r1_reserve(state, operation):
    intent = r1_intent(operation, state)
    if intent is None:
        # Once any guarded operation has been registered, permitting a plain
        # legacy operation would bypass durable cross-cycle deduplication.
        # Structured merge intents remain gated by authenticated recovery.
        if r1_ledger(state)["operations"] and not operation.lstrip().startswith("{"):
            raise Blocked("legacy external reservation forbidden after R1 enrollment")
        return
    ledger = r1_ledger(state)
    operation_id, effect_id = intent["operation_id"], intent["effect_id"]
    if operation_id in ledger["operations"] or effect_id in ledger["effects"]:
        raise Blocked("globally reserved or completed operation/effect replay")
    # The pre-effect reservation is written with the same registry CAS as pending.
    ledger["operations"][operation_id] = {
        "cycle_id": state["cycle"], "effect_id": effect_id,
        "status": "reserved"}
    ledger["effects"][effect_id] = operation_id
    state["r1_guard"] = ledger



def r3_verify_signed_receipt(receipt):
    """Verify Ed25519 evidence against independently configured PUBLIC keys.

    No private key is loaded here. Untrusted key IDs, revoked keys, missing
    trust roots, legacy HMAC signatures and altered payloads fail closed.
    A signature proves verifier-key possession, not external outcome by itself.
    """
    import base64
    import binascii

    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise Blocked("R3 Ed25519 verifier dependency unavailable") from exc

    attestation = receipt.get("attestation")
    if (not isinstance(attestation, dict) or set(attestation) !=
            {"scheme", "key_id", "signature"} or
            attestation.get("scheme") != "ed25519" or
            not isinstance(attestation.get("key_id"), str) or
            not re.fullmatch(r"[a-zA-Z0-9_.:-]{8,128}", attestation["key_id"]) or
            not isinstance(attestation.get("signature"), str)):
        raise Blocked("R3 Ed25519 attestation required; no algorithm downgrade")
    raw_trust = os.environ.get("OFC_R3_TRUSTED_KEYS_JSON", "")
    if not raw_trust:
        raise Blocked("R3 trusted public key configuration missing")
    try:
        trust = json.loads(raw_trust)
    except (TypeError, ValueError) as exc:
        raise Blocked("R3 invalid trusted public key configuration") from exc
    if (not isinstance(trust, dict) or set(trust) !=
            {"agent", "keys", "revoked"} or trust.get("agent") != AGENT or
            not isinstance(trust.get("keys"), dict) or
            not isinstance(trust.get("revoked"), list) or
            any(not isinstance(x, str) for x in trust["revoked"]) or
            len(set(trust["revoked"])) != len(trust["revoked"])):
        raise Blocked("R3 trust root is malformed or not agent-bound")
    key_id = attestation["key_id"]
    if key_id in trust["revoked"]:
        raise Blocked("R3 signing key revoked")
    encoded_key = trust["keys"].get(key_id)
    if not isinstance(encoded_key, str):
        raise Blocked("R3 unknown trusted signing key")
    try:
        public_key_bytes = base64.b64decode(encoded_key, validate=True)
        signature_bytes = base64.b64decode(attestation["signature"], validate=True)
        if len(public_key_bytes) != 32 or len(signature_bytes) != 64:
            raise ValueError("unexpected Ed25519 public key/signature length")
        pubkey = Ed25519PublicKey.from_public_bytes(public_key_bytes)
    except (ValueError, binascii.Error) as exc:
        raise Blocked("R3 malformed trusted public key or signature") from exc
    payload = dict(receipt)
    del payload["attestation"]
    message = (b"OFC-R3-RECEIPT-V1\x00" + AGENT.encode("ascii") + b"\x00" +
               json.dumps(payload, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8"))
    try:
        pubkey.verify(signature_bytes, message)
    except InvalidSignature as exc:
        raise Blocked("R3 Ed25519 receipt signature invalid") from exc
    return True


def r1_record(state, operation, evidence):
    intent = r1_intent(operation, state)
    if intent is None:
        raise Blocked("merge operations require authenticated recovery, not generic record")
    try:
        receipt = json.loads(evidence)
    except (TypeError, ValueError) as exc:
        raise Blocked("invalid R1 receipt JSON") from exc
    required = {"protocol", "agent", "cycle_id", "operation_id",
                "effect_id", "source", "receipt_id", "proof", "attestation"}
    if (not isinstance(receipt, dict) or set(receipt) != required or
            receipt["protocol"] != R1_RECEIPT or receipt["agent"] != AGENT or
            any(receipt[k] != intent[k] for k in
                ("agent", "cycle_id", "operation_id", "effect_id", "source")) or
            not isinstance(receipt["receipt_id"], str) or
            not R1_ID.fullmatch(receipt["receipt_id"]) or
            not isinstance(receipt["proof"], str) or not receipt["proof"].strip()):
        raise Blocked("R1 receipt is not bound to reserved cycle/operation/effect")
    r3_verify_signed_receipt(receipt)
    ledger = r1_ledger(state)
    id_ = intent["operation_id"]
    reserved = ledger["operations"].get(id_)
    if (reserved != {"cycle_id": state["cycle"],
                     "effect_id": intent["effect_id"], "status": "reserved"} or
            ledger["effects"].get(intent["effect_id"]) != id_):
        raise Blocked("R1 reservation record missing or inconsistent")
    if receipt["receipt_id"] in ledger["receipts"]:
        raise Blocked("global receipt ID replay")
    fingerprint = hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    ledger["operations"][id_] = {
        "cycle_id": state["cycle"], "effect_id": intent["effect_id"],
        "status": "recorded", "receipt_id": receipt["receipt_id"],
        "receipt_sha256": fingerprint}
    ledger["receipts"][receipt["receipt_id"]] = id_
    state["r1_guard"] = ledger


def r1_note_verified_merge(state, operation, evidence):
    """Add global tombstones only after recover_merged_pr verified the merge."""
    if not isinstance(operation, str) or not operation.lstrip().startswith("{"):
        # Legacy reconcile_expired callers retain their old test contract;
        # the production verified PR path always has structured intent.
        return
    try:
        intent, receipt = json.loads(operation), json.loads(evidence)
    except (ValueError, TypeError) as exc:
        raise Blocked("invalid verified merge identity") from exc
    if not isinstance(intent, dict) or not isinstance(receipt, dict):
        raise Blocked("invalid verified merge objects")
    repository, pr, op = (intent.get("repository"), intent.get("pr"),
                          intent.get("operation_id"))
    merge_sha = receipt.get("merge_commit_sha")
    if (not isinstance(repository, str) or
            not isinstance(pr, int) or isinstance(pr, bool) or pr < 1 or
            not isinstance(op, str) or not R1_ID.fullmatch(op) or
            not isinstance(merge_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", merge_sha)):
        raise Blocked("invalid verified merge tombstone")
    effect_id = "github-pr:" + repository + ":" + str(pr)
    ledger = r1_ledger(state)
    if (op in ledger["operations"] or effect_id in ledger["effects"] or
            merge_sha in ledger["receipts"]):
        raise Blocked("verified PR merge or receipt already executed")
    ledger["operations"][op] = {"cycle_id": state["cycle"],
                                "effect_id": effect_id, "status": "recorded",
                                "receipt_id": merge_sha,
                                "receipt_sha256": hashlib.sha256(
                                    evidence.encode("utf-8")).hexdigest()}
    ledger["effects"][effect_id] = op
    ledger["receipts"][merge_sha] = op
    state["r1_guard"] = ledger


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
            # Persist all new R1 operation/effect/receipt tombstones across cycles.
            previous_r1 = json.loads(json.dumps(r1_ledger(state))) if state else r1_ledger({})
            state = dict(schema=1, agent=AGENT, cycle=uuid.uuid4().hex, source=source,
                         phase="open", generation=state.get("generation", 0),
                         checkpoint=None, pending=None, results={},
                         r1_guard=previous_r1)
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
        if state["pending"].lstrip().startswith("{"):
            r1_record(state, key, evidence)
        state["results"][key] = evidence
        state["pending"] = None
    elif state["pending"]:
        raise Blocked("external outcome unresolved")
    elif command == "reserve":
        if not value or "=" in value or value in state["results"]:
            raise Blocked("invalid or previously executed operation")
        r1_reserve(state, value)
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
        if os.path.isdir(remote):
            # Disposable bare Git fixtures must be read from their own object store.
            # A shared checkout object store is not reliable on Windows runners.
            assert_canonical_registry_tree(remote, previous)
            raw_state = git("--git-dir=" + remote, "show", previous + ":state.json")
        else:
            git("fetch", "--quiet", "--no-tags", remote, REF)
            if git("rev-parse", "FETCH_HEAD") != previous:
                raise Blocked("registry ref changed while fetching")
            assert_canonical_registry_tree(remote, previous)
            raw_state = git("show", previous + ":state.json")
        state = json.loads(raw_state)
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
    r1_note_verified_merge(recovered, operation, evidence)
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
    if api_fetch is not None and not os.path.isdir(remote):
        raise Blocked("API response injection is forbidden for production recovery")
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
    assert_canonical_registry_tree(remote, previous)
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
