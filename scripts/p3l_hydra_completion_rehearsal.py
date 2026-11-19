"""Durable completion admission for a controlled Hydra rehearsal."""
from contextlib import closing
import json
import sqlite3

from p3l_hydra_fast_lane_gate import SHA64, select_lanes


class CompletionRegistry:
    def __init__(self, path, plan):
        proposal = select_lanes(plan)
        self.path = path
        with closing(sqlite3.connect(path, timeout=10)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS plan (id INTEGER PRIMARY KEY, sha TEXT, data TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS receipts (run_id INTEGER, job_id INTEGER, "
                       "task TEXT UNIQUE, sha TEXT, PRIMARY KEY (run_id, job_id))")
            db.execute("INSERT OR IGNORE INTO plan VALUES (1, ?, ?)",
                       (proposal["input_sha256"], json.dumps(plan)))
            actual, = db.execute("SELECT sha FROM plan WHERE id=1").fetchone()
            if actual != proposal["input_sha256"]:
                raise ValueError("rehearsal database belongs to a different input plan")

    def complete(self, event, independently_verify):
        if (type(event) is not dict or set(event) != {"task", "head", "run_id", "job_id"}
                or type(event["task"]) is not str or type(event["head"]) is not str
                or any(type(event[k]) is not int or not 0 < event[k] <= 2**63-1
                       for k in ("run_id", "job_id"))):
            raise ValueError("invalid completion event identity")
        event = dict(event)
        proof = independently_verify(dict(event))
        if (type(proof) is not dict or proof.get("passed") is not True
                or any(type(proof.get(k)) is not type(v) or proof[k] != v for k, v in event.items())
                or type(proof.get("sha256")) is not str or SHA64.fullmatch(proof["sha256"]) is None):
            raise ValueError("completion is not independently verified")
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            raw, = db.execute("SELECT data FROM plan WHERE id=1").fetchone()
            plan = json.loads(raw)
            if event["head"] != plan["head_sha"]:
                raise ValueError("completion HEAD is stale")
            prior = db.execute("SELECT task, sha FROM receipts WHERE run_id=? AND job_id=?",
                               (event["run_id"], event["job_id"])).fetchone()
            if prior is not None:
                if prior != (event["task"], proof["sha256"]):
                    raise ValueError("completion identity already has a different receipt")
                return {"accepted": False, "eligible": []}
            task = next((item for item in plan["tasks"] if item["key"] == event["task"]), None)
            if task is None or task["state"] != "running":
                raise ValueError("completion does not identify a running task")
            task["state"] = "passed"
            task["evidence_sha"] = proof["sha256"]
            eligible = select_lanes(plan)["eligible"]
            db.execute("INSERT INTO receipts VALUES (?, ?, ?, ?)",
                       (event["run_id"], event["job_id"], event["task"], proof["sha256"]))
            db.execute("UPDATE plan SET data=? WHERE id=1", (json.dumps(plan),))
            return {"accepted": True, "eligible": eligible}
