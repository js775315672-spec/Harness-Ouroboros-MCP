import unittest
from scripts.oril_slot5_cycle_evidence_gate import audit
S='a'*40
H='b'*64
U='https://github.com/example/repo/actions/runs/'
def valid():
    return dict(baseline_sha=S,candidate_sha=S,model_run_url=U+'1',model_output_sha256=H,grader_sha=S,grader_run_url=U+'2',feedback_sha256=H,next_cycle_id='cycle-2',independent_grade='PASS',critical_regressions=0,heldout_evaluation='PASS')
class GateTests(unittest.TestCase):
    def test_complete_is_not_approval(self): self.assertEqual(audit(valid())['status'],'EVIDENCE_COMPLETE_NOT_APPROVED')
    def test_missing_feedback(self):
        r=valid();del r['feedback_sha256'];self.assertEqual(audit(r)['status'],'BLOCKED')
    def test_same_run(self):
        r=valid();r['grader_run_url']=r['model_run_url'];self.assertIn('grader_not_separate_run',audit(r)['errors'])
    def test_failed_heldout(self):
        r=valid();r['heldout_evaluation']='FAIL';self.assertEqual(audit(r)['status'],'BLOCKED')
    def test_missing_gpu_evidence(self):
        r=valid();r['model_weights_improved']=True;self.assertEqual(audit(r)['status'],'BLOCKED')
    def test_bool_regression_rejected(self):
        r=valid();r['critical_regressions']=False;self.assertEqual(audit(r)['status'],'BLOCKED')
    def test_invalid_sha(self):
        r=valid();r['grader_sha']='fake';self.assertEqual(audit(r)['status'],'BLOCKED')
    def test_not_object(self): self.assertEqual(audit([])['status'],'BLOCKED')
if __name__=='__main__': unittest.main()
