"""Adversarial tests: optional local-server module must not leak requests."""
import json
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

from qwen_evolve.grammar import build_in_log_grammar, python_validator
from qwen_evolve.llama_server import LlamaServerClient, build_server_command
from qwen_evolve.passk import unbiased_pass_at_k


class _LocalHandler(BaseHTTPRequestHandler):
    mode = "redirect"
    requests = 0

    def do_POST(self):
        _LocalHandler.requests += 1
        if self.path != "/completion":
            self.send_error(404)
            return
        if self.mode == "redirect":
            self.send_response(302)
            self.send_header("Location", "http://example.com/collect")
            self.end_headers()
        elif self.mode == "oversize":
            payload = json.dumps({"content": "a" * 6401}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif self.mode == "json_non_object":
            payload = b'["unexpected"]'
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif self.mode == "success":
            payload = json.dumps({"content": "hello", "tokens_cached": 8}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    def log_message(self, *args):
        pass


class LocalOnlySecurityTests(unittest.TestCase):
    def test_block_non_loopback_dns_credentials_paths_and_redirected_service(self):
        bad = (
            "http://example.com:8080", "http://localhost:8080",
            "http://127.0.0.1:8080@evil.example:8080",
            "http://name:password@127.0.0.1:8080",
            "http://127.0.0.1:8080/stolen",
            "http://127.0.0.1:8080/?url=http://evil.example",
            "http://127.0.0.1:8080/#fragment",
            "https://127.0.0.1:8080", "http://127.0.0.1",
            "http://10.0.0.1:8080", "http://0.0.0.0:8080",
            "http://127.0.0.1:0",
        )
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                LlamaServerClient(value)
        LlamaServerClient("http://127.0.0.1:8080")
        LlamaServerClient("http://[::1]:8080")

    def test_redirects_never_follow_to_an_external_domain(self):
        server = HTTPServer(("127.0.0.1", 0), _LocalHandler)
        server.timeout = 2
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = LlamaServerClient("http://127.0.0.1:%s" % server.server_port)
            _LocalHandler.mode = "redirect"
            with self.assertRaises(urllib.error.HTTPError) as captured:
                client.complete("test", seed=42)
            self.assertEqual(captured.exception.code, 302)
            self.assertEqual(client.calls, [])
            _LocalHandler.mode = "success"
            self.assertEqual(client.complete("test", seed=42), "hello")
            self.assertEqual(client.calls[-1]["seed"], 42)
            self.assertEqual(client.calls[-1]["tokens_cached"], 8)
            _LocalHandler.mode = "oversize"
            with self.assertRaises(ValueError):
                client.complete("test")
            _LocalHandler.mode = "json_non_object"
            with self.assertRaises(ValueError):
                client.complete("test")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_request_budgets_reject_bad_config_without_http_calls(self):
        client = LlamaServerClient("http://127.0.0.1:8080")
        variants = [
            {"n_predict": 1000}, {"n_predict": True}, {"temperature": -0.1},
            {"temperature": float("nan")}, {"seed": 2**32}, {"seed": True},
            {"grammar": "x" * 9000},
        ]
        for options in variants:
            with self.subTest(options=options), self.assertRaises(ValueError):
                client.complete("anything", **options)
        for options in ({"timeout": 0}, {"timeout": True},
                        {"max_response_bytes": 10}, {"max_response_bytes": 200_000}):
            with self.assertRaises(ValueError):
                LlamaServerClient("http://127.0.0.1:8080", **options)

    def test_speculative_command_is_only_arglist_and_validates_budgets(self):
        argv = build_server_command("llama-server", "model.gguf", draft_gguf="small.gguf")
        self.assertEqual(argv[argv.index("--host") + 1], "127.0.0.1")
        self.assertIn("--model-draft", argv)
        for kwargs in ({"port": True}, {"ctx": 0}, {"threads": 0},
                       {"threads": 200}, {"cache_reuse": -5}):
            with self.assertRaises(ValueError):
                build_server_command("llama-server", "model.gguf", **kwargs)

    def test_restricted_grammar_does_not_prove_semantic_correctness(self):
        v = python_validator()
        self.assertTrue(v.fullmatch('"\\x00" in log or "\\x00" in log'))
        self.assertFalse(v.fullmatch('"\\x10" in log or "\\x00" in log'))
        # Shape alone cannot prove both required control characters are covered.
        self.assertIn("root ::=", build_in_log_grammar())
        self.assertEqual(unbiased_pass_at_k(10, 0, 3), 0.0)


if __name__ == "__main__":
    unittest.main()
