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

    def test_tampered_raw_output(self):
        self.mutate("raw","candidate/ab.json",lambda d: d["rows"][0]["observations"][0].update(output="wrong"))
