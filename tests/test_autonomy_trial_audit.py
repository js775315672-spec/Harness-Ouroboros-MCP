import pathlib
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from autonomy_trial_audit import audit

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
def iso(minutes):
    return (START + timedelta(minutes=minutes)).isoformat()

def event(minutes, kind="verification", commit=None, checks_passed=True, user_prompted=False, attested=True):
    return {"at": iso(minutes), "kind": kind, "commit": commit,
            "checks_passed": checks_passed, "user_prompted": user_prompted, "attested": attested}

class TrialAuditTests(unittest.TestCase):
    def test_thirty_verifications_are_not_development(self):
        result = audit([event(i*2) for i in range(30)], iso(0), iso(60))
        self.assertEqual(result["decision"], "not_proven")
        self.assertEqual(result["actual_code_change_count"], 0)
        self.assertEqual(result["verification_repetitions_excluded"], 30)

    def test_one_code_change_not_enough(self):
        result = audit([event(30, "code_change", "a"*40)], iso(0), iso(60))
        self.assertEqual(result["decision"], "not_proven")

    def test_user_prompted_changes_not_autonomous(self):
        events = [event(i, "code_change", format(i+1, "040x"), user_prompted=True) for i in range(0, 61, 2)]
        self.assertEqual(audit(events, iso(0), iso(60))["decision"], "not_proven")

    def test_self_reported_evidence_never_verified(self):
        events = [event(i, "code_change", format(i+1, "040x")) for i in range(0, 61, 2)]
        events.append(event(30, "next_task"))
        result = audit(events, iso(0), iso(60))
        self.assertEqual(result["decision"], "candidate_requires_independent_attestation")
        self.assertFalse(result["external_attestation_independently_verified"])

    def test_gap_breaks_continuity(self):
        events = [event(0, "code_change", "a"*40), event(60, "code_change", "b"*40),
                  event(30, "next_task")]
        self.assertEqual(audit(events, iso(0), iso(60))["decision"], "not_proven")

    def test_duplicate_commit_rejected(self):
        with self.assertRaises(ValueError):
            audit([event(0, "code_change", "a"*40), event(1, "code_change", "a"*40)], iso(0), iso(60))

    def test_missing_timezone_rejected(self):
        with self.assertRaises(ValueError):
            audit([], "2026-01-01T00:00:00", iso(60))

    def test_short_window_rejected(self):
        with self.assertRaises(ValueError):
            audit([], iso(0), iso(59))

if __name__ == "__main__":
    unittest.main()
