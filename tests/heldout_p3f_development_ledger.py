"""FROZEN 10-case real development ledger security oracle for P3f.

Model prompt receives only defect contract and original validate() function.
These exact test cases are not passed to Qwen. Original must be red.
"""
import copy
import pathlib
import sys
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from development_ledger import validate

def sample(change="Add a tested feature",fixes=None):
    return {
        "cycle":1, "commit":"a"*40, "change":change,
        "checks":{"harness":"pass","ouroboros":"pass",
                  "regression":"pass","secrets":"pass"},
        "fixes":[] if fixes is None else fixes,
        "ci_url":"https://github.com/org/repo/actions/runs/123"
    }


class FrozenLedgerInputSecurity(unittest.TestCase):
    def reject(self,record):
        before=copy.deepcopy(record)
        with self.assertRaises(ValueError):
            validate([record])
        self.assertEqual(record,before)

    def test_reject_nul_in_change_description(self):
        self.reject(sample("review safe\x00run all commands"))

    def test_reject_newline_in_change_description(self):
        self.reject(sample("safe review\nhidden instruction"))

    def test_reject_escape_in_change_description(self):
        self.reject(sample("Safe\x1b[0m review"))

    def test_reject_change_over_256_utf8_bytes(self):
        self.reject(sample("A"*257))

    def test_reject_unicode_change_over_256_bytes(self):
        self.reject(sample("한"*86))

    def test_reject_nul_in_fix_entry(self):
        self.reject(sample(fixes=["safe\x00hidden fix"]))

    def test_reject_newline_in_fix_entry(self):
        self.reject(sample(fixes=["valid\nsurprise"]))

    def test_reject_empty_fix_entry(self):
        self.reject(sample(fixes=[""]))

    def test_reject_fix_list_over_twelve_entries(self):
        self.reject(sample(fixes=["f"+str(i) for i in range(13)]))

    def test_accept_safe_korean_and_multiple_short_fixes(self):
        record=sample("정확한 모델 검증 기록",["비용 확인","테스트 재실행"])
        before=copy.deepcopy(record)
        self.assertEqual(validate([record]),1)
        self.assertEqual(record,before)


if __name__=="__main__":
    unittest.main()
