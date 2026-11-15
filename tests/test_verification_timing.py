import contextlib,io,json,pathlib,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
import verification_cycles
class TimedVerificationTests(unittest.TestCase):
    def test_github_provenance(self):
        data=verification_cycles.run_provenance({'GITHUB_REPOSITORY':'org/repo','GITHUB_RUN_ID':'123','GITHUB_SHA':'a'*40})
        self.assertEqual(data['run_url'],'https://github.com/org/repo/actions/runs/123')
        self.assertIs(data['verified_externally'],False)
    def test_invalid_provenance_fails_closed(self):
        with self.assertRaises(ValueError):
            verification_cycles.run_provenance({'GITHUB_REPOSITORY':'org/repo','GITHUB_RUN_ID':'abc','GITHUB_SHA':'a'*40})
    def test_partial_provenance_fails_closed(self):
        with self.assertRaises(ValueError):
            verification_cycles.run_provenance({'GITHUB_REPOSITORY':'org/repo'})
    def test_zero_run_id_fails_closed(self):
        with self.assertRaises(ValueError):
            verification_cycles.run_provenance({'GITHUB_REPOSITORY':'org/repo','GITHUB_RUN_ID':'0','GITHUB_SHA':'a'*40})
    def test_repository_with_invalid_characters_fails_closed(self):
        with self.assertRaises(ValueError):
            verification_cycles.run_provenance({'GITHUB_REPOSITORY':'org/repo?x=1','GITHUB_RUN_ID':'123','GITHUB_SHA':'a'*40})
    def test_local_provenance(self):
        self.assertEqual(verification_cycles.run_provenance({})['source'],'local')
    def test_success_reports_elapsed_and_rounds(self):
        class Result: returncode=0
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            result=verification_cycles.run(rounds=2,runner=lambda *a,**k:Result())
        lines=[json.loads(x) for x in output.getvalue().splitlines()]
        self.assertEqual(result,0)
        self.assertEqual(lines[-1]["completed_rounds"],2)
        self.assertGreaterEqual(lines[-1]["elapsed_seconds"],0)
        self.assertIn("duration_seconds",lines[0])
    def test_report_file_contains_per_step_timing(self):
        class Result: returncode=0
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/'report.json'
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(verification_cycles.run(rounds=2,runner=lambda *a,**k:Result(),report_path=path),0)
            data=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(len(data['cycles']),2)
            self.assertEqual(len(data['cycles'][0]['steps']),4)
            self.assertIn('duration_seconds',data['cycles'][0]['steps'][0])
    def test_failed_report_is_persisted(self):
        class Result: returncode=1
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/'report.json'
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(verification_cycles.run(rounds=2,runner=lambda *a,**k:Result(),report_path=path),1)
            data=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(data['outcome'],'blocked')
            self.assertEqual(data['failed_round'],1)
    def test_failure_reports_elapsed_and_blocks(self):
        class Result: returncode=1
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            result=verification_cycles.run(rounds=1,runner=lambda *a,**k:Result())
        data=json.loads(output.getvalue())
        self.assertEqual(result,1)
        self.assertEqual(data["completed_rounds"],0)
        self.assertGreaterEqual(data["elapsed_seconds"],0)
        self.assertEqual(data["failed_round"],1)
if __name__=="__main__":unittest.main()
