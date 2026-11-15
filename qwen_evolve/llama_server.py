"""Opt-in, local-only llama-server interface for isolated research.

This module never starts a server and never requests a remote model service.
It intentionally does not replace the frozen Qwen completion benchmark.
Options such as --cache-reuse and --model-draft are NOT claimed compatible with
our pinned llama.cpp revision until a real binary --help/launch test succeeds.
"""
import ipaddress
import json
import math
import urllib.error
import urllib.request
from urllib.parse import urlparse


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Redirects to arbitrary hosts must never bypass the loopback gate."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _require_loopback(base_url):
    if not isinstance(base_url, str) or len(base_url) > 200:
        raise ValueError("invalid bounded server URL")
    try:
        parsed = urlparse(base_url)
        host = parsed.hostname or ""
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid loopback URL") from exc
    if (parsed.scheme != "http" or parsed.username is not None or
            parsed.password is not None or parsed.path not in ("", "/") or
            parsed.params or parsed.query or parsed.fragment or
            port is None or not 1024 <= port <= 65535):
        raise ValueError("server URL must be a bare HTTP loopback origin")
    # Numeric IPs only: localhost DNS resolution is intentionally not used.
    try:
        addr = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("numeric loopback IP required") from exc
    if not addr.is_loopback:
        raise ValueError("llama-server must be loopback-only")
    return parsed


def build_server_command(cli, gguf, port=8080, ctx=2048, threads=4,
                         draft_gguf=None, cache_reuse=256):
    """Return an argv list (never a shell command); does NOT run it.

    Caller must verify flags against the *pinned* binary. Draft GGUF is opt-in
    and must be independently provenance-verified before a caller starts it.
    """
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("invalid port")
    if type(ctx) is not int or not 128 <= ctx <= 16384:
        raise ValueError("invalid context size")
    if type(threads) is not int or not 1 <= threads <= 64:
        raise ValueError("invalid CPU thread count")
    if type(cache_reuse) is not int or not 0 <= cache_reuse <= 2048:
        raise ValueError("invalid bounded cache reuse")
    if not isinstance(cli, (str, bytes)) and not hasattr(cli, "__fspath__"):
        raise ValueError("invalid binary path")
    if not str(cli) or not str(gguf):
        raise ValueError("missing binary or model")
    command = [str(cli), "--model", str(gguf), "--host", "127.0.0.1",
               "--port", str(port), "--ctx-size", str(ctx), "--threads", str(threads),
               "--parallel", "1", "--cache-reuse", str(cache_reuse)]
    if draft_gguf is not None:
        if not str(draft_gguf):
            raise ValueError("invalid speculative model")
        command += ["--model-draft", str(draft_gguf), "--draft-max", "8"]
    return command


class LlamaServerClient:
    """Requests are restricted to a numeric loopback endpoint, without proxies."""

    def __init__(self, base_url="http://127.0.0.1:8080", timeout=150,
                 max_response_bytes=64_000):
        _require_loopback(base_url)
        if type(timeout) is not int or not 10 <= timeout <= 240:
            raise ValueError("invalid bounded inference timeout")
        if type(max_response_bytes) is not int or not 512 <= max_response_bytes <= 100_000:
            raise ValueError("invalid server response size limit")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes
        # No OS proxy support. Redirect handler blocks location changes.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                                   _NoRedirect())
        self.calls = []

    def complete(self, prompt, *, grammar=None, n_predict=140, temperature=0.0, seed=-1):
        if not isinstance(prompt, str) or not 1 <= len(prompt.encode("utf-8")) <= 5000:
            raise ValueError("invalid prompt budget")
        if grammar is not None and (not isinstance(grammar, str) or
                                    not 1 <= len(grammar.encode("utf-8")) <= 8192):
            raise ValueError("invalid GBNF budget")
        if type(n_predict) is not int or not 1 <= n_predict <= 512:
            raise ValueError("invalid token budget")
        if type(temperature) not in (float, int) or not math.isfinite(temperature) or not 0 <= temperature <= 1.0:
            raise ValueError("invalid temperature")
        if type(seed) is not int or not -1 <= seed <= 2**31 - 1:
            raise ValueError("invalid seed")
        body = {"prompt": prompt, "n_predict": n_predict, "temperature": temperature,
                "seed": seed, "cache_prompt": True}
        if grammar is not None:
            body["grammar"] = grammar
        request = urllib.request.Request(
            self.base_url + "/completion", data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with self._opener.open(request, timeout=self.timeout) as response:
            payload = response.read(self.max_response_bytes + 1)
        if len(payload) > self.max_response_bytes:
            raise ValueError("server response exceeds budget")
        data = json.loads(payload.decode("utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("content"), str):
            raise ValueError("malformed server response")
        content = data["content"]
        if len(content.encode("utf-8")) > 6000:
            raise ValueError("unbounded model answer")
        self.calls.append({"temperature": temperature, "seed": seed,
                           "grammar": grammar is not None,
                           "tokens_cached": data.get("tokens_cached") if type(data.get("tokens_cached")) is int else None,
                           "timings": data.get("timings") if isinstance(data.get("timings"), dict) else None})
        return content
