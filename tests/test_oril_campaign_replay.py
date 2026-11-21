import json
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import unittest
from zipfile import ZipFile

from oril.checkpoint import replay, sha

ARCHIVE = Path(__file__).resolve().parents[1] / "docs/oril/evidence/44852655575"


class CampaignReplayTests(unittest.TestCase):
    def test_full_public_chain(self):
        self.assertEqual(replay(ARCHIVE), 360)

    def mutate(self, kind, key, change):
        with TemporaryDirectory() as temp:
            folder = Path(temp) / "run"
            shutil.copytree(ARCHIVE, folder)
            path = folder / f"{kind}-2.zip"
            with ZipFile(path) as archive:
                entries = {name:archive.read(name) for name in archive.namelist()}
            data = json.loads(entries[key])
            change(data)
            entries[key] = json.dumps(data).encode()
            with ZipFile(path,"w") as archive:
                for name, value in entries.items():
                    archive.writestr(name,value)
            ledger = json.loads((folder/"ledger.json").read_text(encoding="utf-8"))
            ledger["cycles"][1][kind]["sha256"] = sha(path.read_bytes())
            (folder/"ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
            with self.assertRaises(ValueError):
                replay(folder)

    def test_forged_public_audit(self):
        self.mutate("review","audit.json",lambda d: d["ab"]["public_exact_matches"].update(compact=30))

    def test_forged_approval(self):
        self.mutate("review","memory.json",lambda d: d.update(promotion_allowed=True))

    def test_swapped_parent(self):
        self.mutate("raw","input/memory.json",lambda d: d.update(candidate_errors=0))

    def forge_final_candidate(self, change):
        with TemporaryDirectory() as temp:
            folder = Path(temp) / "run"
            shutil.copytree(ARCHIVE, folder)
            raw_path = folder / "raw-3.zip"
            review_path = folder / "review-3.zip"
            with ZipFile(raw_path) as archive:
                raw_entries = {name: archive.read(name) for name in archive.namelist()}
            candidate = json.loads(raw_entries["candidate/candidate.json"])
            change(candidate)
            raw_entries["candidate/candidate.json"] = json.dumps(candidate).encode()
            with ZipFile(raw_path, "w") as archive:
                for name, value in raw_entries.items():
                    archive.writestr(name, value)
            with ZipFile(review_path) as archive:
                review_entries = {name: archive.read(name) for name in archive.namelist()}
            memory = json.loads(review_entries["memory.json"])
            memory["evidence_sha256"] = sha(raw_entries["candidate/candidate.json"])
            review_entries["memory.json"] = json.dumps(memory).encode()
            with ZipFile(review_path, "w") as archive:
                for name, value in review_entries.items():
                    archive.writestr(name, value)
            ledger_path = folder / "ledger.json"
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            ledger["cycles"][2]["raw"]["sha256"] = sha(raw_path.read_bytes())
            ledger["cycles"][2]["review"]["sha256"] = sha(review_path.read_bytes())
            ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "planned prompt binding|hypothesis identity"):
                replay(folder)

    def test_rejects_self_consistent_prompt_substitution(self):
        def forge(candidate):
            candidate["prompt"] = "Return a different answer."
            candidate["candidate_sha"] = sha(candidate["prompt"].encode())
        self.forge_final_candidate(forge)

    def test_rejects_hypothesis_relabeling(self):
        self.forge_final_candidate(lambda c: c.update(hypothesis_id="unapproved_strategy"))

    def test_tampered_raw_output(self):
        self.mutate("raw","candidate/ab.json",lambda d: d["rows"][0]["observations"][0].update(output="wrong"))
