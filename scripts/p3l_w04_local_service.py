"""Loopback transport for rehearsing W04 workers against one durable registry."""
import argparse
from dataclasses import asdict
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3

from p3l_w04_attempt_registry import AttemptBlocked, AttemptInput, AttemptRegistry, Lease
from p3l_w04_github_claim import SharedBudget, github

MAX_BODY = 4096
LOOPBACK = "127.0.0.1"


def unique_object(pairs):
    obj = dict(pairs)
    if len(obj) != len(pairs):
        raise ValueError("duplicate JSON field")
    return obj


def read_registry_object(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("missing or unsafe registry input")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BODY + 1)
    if not 1 <= len(raw) <= MAX_BODY:
        raise ValueError("invalid registry input size")
    value = json.loads(raw, object_pairs_hook=unique_object)
    if type(value) is not dict:
        raise ValueError("expected registry input object")
    return value


class _RegistryHandler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(15)
        super().setup()

    def log_message(self, format, *args):
        pass

    def _reply(self, status, body):
        payload = json.dumps(body, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        address = f"{LOOPBACK}:{self.server.server_port}"
        if (self.headers.get_all("Host") != [address] or self.headers.get("Origin") is not None
                or self.headers.get_all("Content-Type") != ["application/json"]
                or self.headers.get("Transfer-Encoding") is not None):
            self._reply(400, {"error": "invalid local request headers"})
            return
        lengths = self.headers.get_all("Content-Length", [])
        if (len(lengths) != 1 or len(lengths[0]) > 4 or not lengths[0].isascii()
                or not lengths[0].isdigit() or not 0 < int(lengths[0]) <= MAX_BODY):
            self._reply(400, {"error": "invalid local request length"})
            return

        try:
            body = json.loads(self.rfile.read(int(lengths[0])), object_pairs_hook=unique_object)
            if type(body) is not dict:
                raise ValueError("expected request object")
            registry = self.server.registry
            if self.path in {"/reserve", "/status"}:
                body["inputs"] = AttemptInput(**body["inputs"])
                result = (asdict(registry.reserve(**body)) if self.path == "/reserve"
                          else registry.status(**body))
            elif self.path == "/start":
                shared = self.server.shared_budget
                required = body.pop("require_shared", False)
                if type(required) is not bool or required != (shared is not None):
                    raise AttemptBlocked("requested admission mode differs from coordinator mode")
                body["lease"] = Lease(**body["lease"])
                if shared is not None:
                    shared.require_match(**body)
                registry.start(**body)
                result = {"started": True}
                if shared is not None:
                    # Either store may be spent if the provider or acknowledgement fails.
                    shared.record()
                    status = registry.status(shared.inputs)
                    if status is None or status["state"] != "STARTED":
                        raise AttemptBlocked("lease expired before shared admission completed")
                    result["shared"] = True
            else:
                self._reply(404, {"error": "unknown registry route"})
                return
        except AttemptBlocked as error:
            self._reply(409, {"error": str(error)})
            return
        except (ValueError, TypeError, KeyError, OverflowError):
            self._reply(400, {"error": "invalid registry request"})
            return
        except (sqlite3.Error, OSError, HTTPException):
            self._reply(503, {"error": "registry unavailable"})
            return
        self._reply(200, result)


class RegistryServer(ThreadingHTTPServer):
    def __init__(self, registry, port=0, *, shared_budget=None):
        self.registry = registry
        self.shared_budget = shared_budget
        super().__init__((LOOPBACK, port), _RegistryHandler)


class RegistryClient:
    def __init__(self, port, *, timeout=15, require_shared=False):
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("invalid registry port")
        if type(require_shared) is not bool:
            raise ValueError("invalid shared admission mode")
        self.port = port
        self.timeout = timeout
        self.require_shared = require_shared

    def _request(self, route, payload):
        conn = HTTPConnection(LOOPBACK, self.port, timeout=self.timeout)
        try:
            headers = {"Host": f"{LOOPBACK}:{self.port}", "Content-Type": "application/json"}
            conn.request("POST", route, json.dumps(payload).encode(), headers)
            response = conn.getresponse()
            body = response.read(MAX_BODY + 1)
            if len(body) > MAX_BODY or response.status != 200:
                raise AttemptBlocked(f"registry did not admit request (HTTP {response.status})")
            return json.loads(body, object_pairs_hook=unique_object)
        finally:
            conn.close()

    def reserve(self, inputs, owner, *, ttl_seconds):
        return Lease(**self._request("/reserve", {"inputs": asdict(inputs), "owner": owner,
                                                  "ttl_seconds": ttl_seconds}))

    def status(self, inputs):
        return self._request("/status", {"inputs": asdict(inputs)})

    def start(self, lease, *, observed_head, run_id):
        payload = {"lease": asdict(lease), "observed_head": observed_head, "run_id": run_id}
        expected = {"started": True}
        if self.require_shared:
            payload["require_shared"] = True
            expected["shared"] = True
        result = self._request("/start", payload)
        if type(result) is not dict or set(result) != set(expected) or any(value is not True for value in result.values()):
            raise AttemptBlocked("registry start acknowledgement is invalid")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--shared-attempt", type=Path)
    args = parser.parse_args()
    shared = None
    if args.shared_attempt is not None:
        config = read_registry_object(args.shared_attempt)
        if set(config) != {"inputs", "run_id"}:
            parser.error("invalid shared attempt fields")
        token = os.environ.get("GH_TOKEN")
        if not token:
            parser.error("shared admission requires a coordinator token")
        shared = SharedBudget(AttemptInput(**config["inputs"]), config["run_id"],
                              lambda *request: github(token, *request))
    with RegistryServer(AttemptRegistry(args.database), args.port, shared_budget=shared) as server:
        print(f"W04 local registry listening on {LOOPBACK}:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
