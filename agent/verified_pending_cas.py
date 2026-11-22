"""DEV-only bridge: independently verified ZIP -> pending receipt -> fenced CAS.

No production remote, token, or OPS registry is configured by this module.
Caller supplies a trusted read-only artifact lookup and a remote explicitly.
"""
import json
import re
from agent import cycle_registry as registry
from agent.artifact_integrity import verify_zip
from agent.pending_reconcile import Observation, reconcile

SHA = re.compile(r"^[0-9a-f]{40}$")

def verified_receipt(artifact, *, repo, run_id, head_sha, fetch):
    """Create an auditable receipt only after the actual ZIP passes verification."""
    digest = verify_zip(artifact, repo=repo, run_id=run_id,
                        head_sha=head_sha, fetch=fetch)
    return json.dumps({"artifact_id": artifact["id"], "digest": digest,
                       "head_sha": head_sha, "repo": repo, "run_id": run_id},
                      sort_keys=True, separators=(",", ":"))

def reconcile_to_isolated_remote(remote, *, owner, generation, source, now,
                                 lookup, verify, expected_pending):
    """CAS commit of a verified pending operation; never retry the side effect.

    A remote is mandatory and the repository's configured production remote is
    forbidden. An authenticated read-only lookup and independent verifier must
    be supplied. A competing writer causes BLOCKED via the git lease.
    """
    if not remote or remote == registry.REMOTE or "github.com" in remote.lower():
        raise registry.Blocked("production or unspecified remote forbidden")
    if not SHA.fullmatch(source):
        raise registry.Blocked("invalid pinned source")
    if not callable(lookup) or not callable(verify):
        raise registry.Blocked("independent evidence callbacks required")
    before = registry.transact(remote, "inspect")
    if before.get("pending") != expected_pending:
        raise registry.Blocked("pending changed or already reconciled")
    after = reconcile(before, owner=owner, generation=generation, source=source,
                      now=now, lookup=lookup, verify=verify)
    if after.get("pending") is not None:
        raise registry.Blocked("pending was not cleared")
    receipt = after["results"][expected_pending]
    if not receipt:
        raise registry.Blocked("empty verified receipt")
    # The registry performs a fresh read + pinned-main check + atomic Git lease.
    # Never write the candidate state directly, avoiding lost updates.
    return registry.transact(remote, "record", owner=owner,
                             generation=generation, source=source,
                             value=expected_pending + "=" + receipt)
