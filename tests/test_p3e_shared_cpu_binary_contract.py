"""Offline tests for safe one-build, eight-independent consumers (NO GGUF)."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=ROOT/".github/workflows/p3e-once-build-eight-fanout.yml"


class SharedPinnedBuildContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.y=WORKFLOW.read_text(encoding="utf-8")

    def test_only_one_actual_cpp_compilation(self):
        self.assertEqual(self.y.count("cmake --build "),1)

    def test_only_one_git_fetch_of_pinned_upstream_source(self):
        self.assertEqual(self.y.count("git -C vendor/llama.cpp fetch"),1)
        self.assertIn("4e5116f47619dac4180c3007ef02a383f347554c",self.y)

    def test_zero_model_inference_and_zero_gguf_weights(self):
        self.assertIn('"model_calls":0',self.y)
        self.assertIn('"model_weights_included":False',self.y)
        self.assertNotIn("gguf_official_download.py",self.y)
        self.assertNotIn("--n-predict",self.y)

    def test_all_eight_lanes_are_separately_allocated(self):
        self.assertIn('["01", "02", "03", "04", "05", "06", "07", "08"]',self.y)
        self.assertIn("max-parallel: 8",self.y)

    def test_artifact_is_same_run_not_global_cache(self):
        self.assertIn("cache-mode: none",self.y)
        self.assertNotIn("actions/cache@",self.y)
        self.assertIn("p3e-pinned-llama-completion-same-run",self.y)

    def test_exact_pinned_artifact_actions(self):
        self.assertIn("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",self.y)
        self.assertIn("actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093",self.y)

    def test_verified_review_commit_is_bound_at_consumers(self):
        self.assertIn('"review_sha":os.environ["REVIEW_SHA"]',self.y)
        self.assertIn('"upstream_sha":os.environ["PINNED_LLAMA_SHA"]',self.y)

    def test_same_run_binary_digest_verified_before_execution(self):
        self.assertIn('hashlib.sha256(binary.read_bytes()).hexdigest()',self.y)
        i=self.y.index('assert type(data) is dict and data==expected')
        e=self.y.index("llama-completion --help")
        self.assertLess(i,e)

    def test_no_creds_or_privileged_token(self):
        self.assertIn("persist-credentials: false",self.y)
        self.assertNotIn("contents: write",self.y)
        self.assertNotIn("pull-requests: write",self.y)
        self.assertNotIn("secrets.",self.y)

    def test_only_safe_invocation_triggers(self):
        self.assertIn("pull_request:",self.y)
        self.assertIn("workflow_dispatch:",self.y)
        self.assertNotIn("pull_request_target:",self.y)
        self.assertNotIn("schedule:",self.y)

    def test_binary_has_explicit_size_cap(self):
        self.assertIn("100_000_000",self.y)
        self.assertIn("1_000_000",self.y)

    def test_pinned_checkout_and_source_sha(self):
        self.assertIn("actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",self.y)
        self.assertIn('test "$(git -C vendor/llama.cpp rev-parse HEAD)" = "$PINNED_LLAMA_SHA"',self.y)

    def test_no_auto_promotion_even_after_eight_green(self):
        self.assertIn('"merge_authorized":False',self.y)
        self.assertIn('"repo_writes_authorized":False',self.y)
        self.assertNotIn("gh pr merge",self.y)

    def test_all_results_checked_and_fail_closed(self):
        self.assertIn('test "$BUILD_RESULT" = success',self.y)
        self.assertIn('test "$FANOUT_RESULT" = success',self.y)

    def test_group_has_read_only_permissions(self):
        self.assertGreaterEqual(self.y.count("contents: read"),3)
        self.assertIn("NO_UNTRUSTED_BINARY_CACHE",self.y)

    def test_run_is_explicitly_not_an_ai_coding_success(self):
        self.assertIn("0 LLM calls",self.y)
        self.assertIn('"model_calls":0',self.y)


if __name__=="__main__":
    unittest.main()
