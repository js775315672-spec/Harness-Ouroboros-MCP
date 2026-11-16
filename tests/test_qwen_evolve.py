import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from qwen_evolve.grammar import build_in_log_grammar, python_validator
from qwen_evolve.llama_server import LlamaServerClient, build_server_command
from qwen_evolve.passk import pass_rate_wilson, unbiased_pass_at_k
from qwen_evolve.repair_loop import Verdict, run_bounded_repair, sanitize_feedback


class GrammarTests(unittest.TestCase):
    def test_grammar_text(self):
        g = build_in_log_grammar()
        self.assertIn('root ::= clause " or " clause', g)
        self.assertIn('byte ::= "\\\\x00" | "\\\\x1b"', g)

    def test_validator_accepts_only_target_shape(self):
        v = python_validator()
        good = '"\\x00" in log or "\\x1b" in log'
        self.assertTrue(v.match(good))
        self.assertTrue(v.match('"\\x1b" in log or "\\x00" in log'))
        for bad in ['"\x00" in log or "\x1b" in log',
                    '```python\n' + good + '\n```',
                    'Use: ' + good, '"\\x00" in log',
                    '"\\x41" in log or "\\x00" in log',
                    good + ' or __import__("os")']:
            self.assertFalse(v.match(bad), bad)

    def test_bounds_and_inputs_rejected(self):
        for kwargs in ({"allowed_hex": ()}, {"allowed_hex": ("zz",)},
                       {"min_clauses": 3, "max_clauses": 2}, {"variable": "a b"}):
            with self.assertRaises(ValueError):
                build_in_log_grammar(**kwargs)

    def test_optional_clauses(self):
        g = build_in_log_grammar(min_clauses=1, max_clauses=3)
        self.assertIn('root ::= clause (" or " clause)? (" or " clause)?', g)


class RepairLoopTests(unittest.TestCase):
    GOOD = '"\\x00" in log or "\\x1b" in log'

    def setUp(self):
        self.verifier = lambda r: Verdict(r == self.GOOD, "ast_gate", "shape mismatch \x1b[31m")

    def test_feedback_changes_next_prompt_and_passes(self):
        prompts = []
        def generate(prompt, temperature, seed):
            prompts.append(prompt)
            return "nonsense" if len(prompts) == 1 else self.GOOD
        result = run_bounded_repair(generate, self.verifier, "BASE")
        self.assertTrue(result.passed)
        self.assertEqual(result.model_calls, 2)
        self.assertIn("rejected at stage 'ast_gate'", prompts[1])
        self.assertNotIn("\x1b", prompts[1])

    def test_duplicates_not_reverified_and_budget_hard(self):
        calls = {"verify": 0}
        def verify(r):
            calls["verify"] += 1
            return Verdict(False, "ast_gate", "no")
        result = run_bounded_repair(lambda p, temperature, seed: "same", verify, "B")
        self.assertFalse(result.passed)
        self.assertEqual(result.model_calls, 3)
        self.assertEqual(calls["verify"], 1)
        self.assertTrue(result.attempts[1].duplicate)

    def test_temperature_escalates(self):
        seen = []
        run_bounded_repair(lambda p, temperature, seed: seen.append((temperature, seed)) or "x",
                           self.verifier, "B")
        self.assertEqual(seen, [(0.0, 0), (0.4, 11), (0.7, 23)])

    def test_budget_limits(self):
        with self.assertRaises(ValueError):
            run_bounded_repair(None, None, "B", schedule=())

    def test_sanitize(self):
        self.assertEqual(sanitize_feedback("a\x00b\x1b[0m\n\n c", 50), "a?b?[0m c")
        self.assertEqual(len(sanitize_feedback("x" * 999, 300)), 300)


class _Handler(BaseHTTPRequestHandler):
    captured = {}

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Handler.captured = body
        out = json.dumps({"content": "ok", "tokens_cached": 7}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


class ServerClientTests(unittest.TestCase):
    def test_loopback_enforced(self):
        for url in ("http://example.com:8080", "https://127.0.0.1", "http://10.0.0.5:8080"):
            with self.assertRaises(ValueError):
                LlamaServerClient(url)

    def test_request_shape_with_fake_server(self):
        server = HTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            client = LlamaServerClient("http://127.0.0.1:%d" % server.server_port)
            text = client.complete("hi", grammar='root ::= "a"', temperature=0.4, seed=11)
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(text, "ok")
        sent = _Handler.captured
        self.assertTrue(sent["cache_prompt"])
        self.assertEqual((sent["temperature"], sent["seed"]), (0.4, 11))
        self.assertIn("grammar", sent)
        self.assertEqual(client.calls[0]["tokens_cached"], 7)

    def test_server_command_is_loopback_no_shell_list(self):
        cmd = build_server_command("llama-server", "m.gguf", draft_gguf="d.gguf")
        self.assertEqual(cmd[cmd.index("--host") + 1], "127.0.0.1")
        self.assertIn("--model-draft", cmd)
        with self.assertRaises(ValueError):
            build_server_command("s", "m", port=80)


class PassKTests(unittest.TestCase):
    def test_wilson_and_passk(self):
        p, lo, hi = pass_rate_wilson(18, 20)
        self.assertAlmostEqual(p, 0.9)
        self.assertTrue(lo < p < hi <= 1.0)
        self.assertEqual(unbiased_pass_at_k(10, 0, 3), 0.0)
        self.assertEqual(unbiased_pass_at_k(10, 9, 3), 1.0)
        self.assertAlmostEqual(unbiased_pass_at_k(10, 5, 1), 0.5)
        with self.assertRaises(ValueError):
            pass_rate_wilson(3, 2)


if __name__ == "__main__":
    unittest.main()
