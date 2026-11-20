import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_tiny_qwen_cpu_paired_benchmark import summarize, run


def pair(short=5, long=12, st=1.5, lt=1.8):
    return {"compact": {"input_tokens": short, "output_tokens": 3,
                        "elapsed_seconds": st},
            "verbose": {"input_tokens": long, "output_tokens": 3,
                        "elapsed_seconds": lt}}


class PairedBenchmarkAudit(unittest.TestCase):
    def test_real_measurement_statistics_not_quality(self):
        r = summarize([pair(), pair(st=1.7, lt=1.6)], "a" * 64)
        self.assertEqual(r["n_pairs"], 2)
        self.assertEqual(r["n_real_generations"], 4)
        self.assertGreater(r["input_token_reduction_pct_median"], 50)
        self.assertFalse(r["pretrained_weights"])
        self.assertFalse(r["performance_gain_verified"])
        self.assertFalse(r["lora_adapter_created"])
        self.assertIsNone(r["model_intelligence_gain"])
        self.assertEqual(r["independent_quality_n"], 0)

    def test_balanced_order(self):
        r = summarize([pair()] * 4, "b" * 64)
        self.assertEqual(r["pair_orders"],
                         ["compact_first", "verbose_first"] * 2)

    def test_missing_variant_rejected(self):
        with self.assertRaises(ValueError):
            summarize([{"compact": pair()["compact"]}], "c" * 64)

    def test_fake_negative_or_nonfinite_elapsed_rejected(self):
        for invalid in (-1, float("nan"), float("inf"), True):
            x = pair()
            x["compact"]["elapsed_seconds"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                summarize([x], "d" * 64)

    def test_wrong_or_reversed_token_count_rejected(self):
        for invalid in (0, True, 12):
            x = pair(short=invalid)
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                summarize([x], "e" * 64)

    def test_zero_pairs_rejected(self):
        with self.assertRaises(ValueError):
            summarize([], "f" * 64)

    def test_unsafe_pair_count_rejected_before_loading_weights(self):
        for count in (0, 1, 21, True, "6"):
            with self.subTest(count=count), self.assertRaises(ValueError):
                run(count)


if __name__ == "__main__":
    unittest.main()
