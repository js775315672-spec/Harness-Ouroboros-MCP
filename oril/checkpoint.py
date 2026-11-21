"""Replay the archived public campaign, including the feedback between jobs."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from oril.orchestrator import SEED, TASKS, WEIGHT, REV, plan
from oril_v2_slot2_public30_independent_audit import audit as audit_ab
from oril_v2_slot4_public30_aa_independent_audit import audit as audit_aa


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check(actual, expected, label):
    if actual != expected:
        raise ValueError(f"invalid {label}")


def replay(folder):
    ledger = json.loads((folder / "ledger.json").read_text(encoding="utf-8"))
    parent = None
    requests = 0
    check(len(ledger["cycles"]), 3, "cycle count")
    for n, row in enumerate(ledger["cycles"], 1):
        for kind in ("raw", "review"):
            check(sha((folder / f"{kind}-{n}.zip").read_bytes()), row[kind]["sha256"], kind)
        with ZipFile(folder / f"raw-{n}.zip") as raw, ZipFile(folder / f"review-{n}.zip") as review:
            cbytes = raw.read("candidate/candidate.json")
            candidate = json.loads(cbytes)
            cid = f"{ledger['run_id']}-{n}"
            check(candidate["cycle_id"], cid, "cycle identity")
            check(candidate["parent_cycle_id"], f"{ledger['run_id']}-{n-1}" if n>1 else None, "parent identity")
            check(candidate["implementation_sha"], ledger["head_sha"], "source")
            check(candidate["base_sha"], ledger["base_sha"], "base")
            check(sha(candidate["prompt"].encode()), candidate["candidate_sha"], "prompt")
            if parent is None:
                seed = raw.read("input/public_30_pairs.json")
                check(sha(seed), SEED, "seed")
                check(candidate["observed_problem"], audit_ab(json.loads(seed))["input_tokens"], "seed metrics")
                memory = {"tried": [], "candidate_errors": 0}
                previous_digest = SEED
            else:
                check(raw.read("input/memory.json"), parent, "copied feedback")
                memory = json.loads(parent)
                check(candidate["observed_problem"], memory["candidate_errors"], "measured failure")
                previous_digest = sha(parent)
            check(candidate["parent_evidence_sha256"], previous_digest, "predecessor digest")
            check(candidate["tried"], memory["tried"] + [plan(memory)], "memory-directed candidate")
            audits = json.loads(review.read("audit.json"))
            for kind, audit in [("ab", audit_ab), ("aa", audit_aa)]:
                data = raw.read(f"candidate/{kind}.json")
                check(sha(data), candidate["raw_sha256"][kind+".json"], "observations")
                report = json.loads(data)
                check((report["resolved_revision"], report["weight_files"][0]["sha256"], report["public_tasks_sha256"]),
                      (REV, WEIGHT, TASKS), "model and data")
                check(audit(report), audits[kind], "public auditor output")
                requests += sum(len(r["observations"]) for r in report["rows"])
            parent = review.read("memory.json")
            m = json.loads(parent)
            ab = audits["ab"]
            regressions = ab["paired_accuracy_discordance"]["verbose_only_correct"]
            check(m["evidence_sha256"], sha(cbytes), "candidate -> memory")
            check((m["cycle_id"], m["tried"], m["candidate_errors"], m["regressions"]),
                  (cid, candidate["tried"], 30-ab["public_exact_matches"]["compact"], regressions), "feedback")
            check(m["state"], "rejected" if regressions or ab["token_saving_pct_descriptive"]<20 else "tested", "state")
            check((m["protected_grade"], m["promotion_allowed"]), ("pending",False), "authorization")
    return requests


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    print(f"Recomputed {replay(parser.parse_args().folder)} public observations")
