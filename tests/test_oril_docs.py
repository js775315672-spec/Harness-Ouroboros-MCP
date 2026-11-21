import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts import oril_docs as d


class DocsTests(unittest.TestCase):
    def setUp(self):
        self.rows = [r for r in d.read_rows(d.LEDGER) if r["schema"] == d.SCHEMA]

    def test_schema_rejects_private_and_unverified_claims(self):
        for k, v in (("candidate_sha", "abc"), ("improvement_verified", True),
                     ("model", "ghp_"+"x"*40), ("private_answer", "value"),
                     ("heldout_score", 1), ("hypothesis", "secret")):
            with self.subTest(k=k), self.assertRaises(Exception):
                d.validate(dict(self.rows[0], **{k: v}))

    def test_artifact_and_source_are_bound(self):
        with patch.object(d, "api", return_value={"head_sha": "0"*40, "jobs": [], "artifacts": []}):
            with self.assertRaisesRegex(ValueError, "unverified run"):
                d.collect(d.ARCHIVE, 44853120822)
        from zipfile import BadZipFile
        with self.assertRaises(BadZipFile):
            d.member(b"corrupt", "audit.json")

    def test_replay_five_deliveries_and_conflicts(self):
        self.assertEqual(d.merge([], self.rows * 5), self.rows)
        self.assertEqual(d.merge(self.rows, list(reversed(self.rows))), [])
        with self.assertRaisesRegex(ValueError, "conflicting"):
            d.merge(self.rows, [dict(self.rows[0], duration_seconds=0)])

    def test_window_and_condition_isolation(self):
        sample = [copy.deepcopy(self.rows[0]) for _ in range(6)]
        for i, row in enumerate(sample):
            row["duration_seconds"] = (10,10,10,20,20,20)[i]
        self.assertEqual(d.trends(sample)[0]["metrics"]["duration_seconds"]["change_pct"], 100)
        for row in sample[3:]:
            row["hypothesis"] = "check_sum"
        self.assertTrue(all(g["metrics"]["duration_seconds"]["median"] is None for g in d.trends(sample)))

    def test_reproducibility_and_latest_record(self):
        paths = [d.LEDGER, d.LESSONS, d.STATUS, d.ROADMAP, d.TRENDS, Path("README.md")]
        before = [p.read_bytes().replace(b"\r\n", b"\n") for p in paths]
        d.generate(self.rows[::-1])
        self.assertEqual(before, [p.read_bytes().replace(b"\r\n", b"\n") for p in paths])
        self.assertIn(self.rows[-1]["cycle_id"], d.STATUS.read_text(encoding="utf-8"))

    def test_context_lookup_against_original_public_receipts(self):
        # Same task: identify repeated public errors for integer_format and its next gate.
        hypothesis = "integer_format"
        start = time.perf_counter()
        source_ids = []
        raw_bytes = 0
        for run in d.SEEDS:
            for n in range(1, 4):
                base = f"{d.ARCHIVE}:docs/oril/evidence/{run}"
                raw = d.git("show", f"{base}/raw-{n}.zip")
                review = d.git("show", f"{base}/review-{n}.zip")
                raw_bytes += len(raw) + len(review)
                candidate = d.member(raw, "candidate/candidate.json")
                memory = d.member(review, "memory.json")
                if candidate["hypothesis_id"] == hypothesis and memory["candidate_errors"]:
                    self.assertEqual(memory["protected_grade"], "pending")
                    source_ids.append(memory["cycle_id"])
        baseline_seconds = time.perf_counter() - start
        start = time.perf_counter()
        context = d.context()
        lesson = next(x for x in context["lessons"] if x["hypothesis"] == hypothesis)
        self.assertEqual(lesson["cycles"], source_ids)
        self.assertEqual(lesson["next_action"], "independent_heldout_review")
        print(json.dumps(dict(task=hypothesis, original_archive_bytes=raw_bytes, context_bytes=len(d.dump(context).encode()),
                              original_seconds=baseline_seconds, context_seconds=time.perf_counter()-start,
                              evidence=source_ids)))
