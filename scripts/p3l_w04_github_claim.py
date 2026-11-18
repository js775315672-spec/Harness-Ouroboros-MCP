"""Create-only GitHub start receipts for the trusted W04 coordinator."""
from collections.abc import Callable
from dataclasses import dataclass
from http.client import HTTPSConnection
import json

from p3l_w04_attempt_registry import AttemptBlocked, AttemptInput, SHA40

REPOSITORY = "js775315672-spec/Harness-Ouroboros-MCP"
API_PATH = f"/repos/{REPOSITORY}/git"
MAX_RESPONSE = 32 * 1024
START_REF_PREFIX = "refs/heads/p3l-w04/started/"
# The #83 ledger attempt consumed this semantic budget before the shared registry existed.
HISTORICAL_LEDGER_KEY = "5f30e457e4d6b57fef177ccca0af7ccc8f169faeb9d45bddf664059ad338ca02"


def github(token, method, route, payload=None):
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
               "Content-Type": "application/json", "User-Agent": "harness-w04-coordinator"}
    connection = HTTPSConnection("api.github.com", timeout=12)
    try:
        connection.request(method, API_PATH + route, body=payload, headers=headers)
        response = connection.getresponse()
        data = response.read(MAX_RESPONSE + 1)
        if len(data) > MAX_RESPONSE:
            raise ValueError("oversized GitHub reference response")
        return response.status, data
    finally:
        connection.close()


def verified_ref(body, expected_ref):
    payload = json.loads(body)
    target = payload.get("object") if type(payload) is dict else None
    if (type(target) is not dict or payload.get("ref") != expected_ref
            or target.get("type") != "commit" or type(target.get("sha")) is not str
            or SHA40.fullmatch(target["sha"]) is None):
        raise ValueError("GitHub response did not identify the exact GitHub ref")
    return target["sha"]


def create_once(ref, head, request):
    """Return a positive receipt only from the original create acknowledgement."""
    status, body = request("POST", "/refs", json.dumps({"ref": ref, "sha": head}).encode())
    if status == 201:
        winner = verified_ref(body, ref)
        if winner != head:
            raise ValueError("created ref differs from requested HEAD")
        return True, status, winner
    if status in (409, 422):
        confirmed, body = request("GET", "/ref/" + ref.removeprefix("refs/"))
        if confirmed != 200:
            raise ValueError("ref conflict has no confirmed durable record")
        return False, status, verified_ref(body, ref)
    raise ValueError(f"ref creation failed with HTTP {status}")


@dataclass(frozen=True)
class SharedBudget:
    inputs: AttemptInput
    run_id: int
    request: Callable

    def __post_init__(self):
        if type(self.run_id) is not int or not 0 < self.run_id <= 2**63 - 1:
            raise ValueError("invalid authorized run id")
        if self.inputs.semantic_key == HISTORICAL_LEDGER_KEY:
            raise AttemptBlocked("historical ledger budget already consumed")

    def require_match(self, lease, observed_head, run_id):
        if (lease.task_key != self.inputs.task_key or observed_head != self.inputs.head_sha
                or type(run_id) is not int or run_id != self.run_id):
            raise AttemptBlocked("start does not match the coordinator's authorized attempt")

    def record(self):
        ref = START_REF_PREFIX + self.inputs.semantic_key
        created, _, _ = create_once(ref, self.inputs.head_sha, self.request)
        if not created:
            raise AttemptBlocked("shared semantic budget already consumed")
