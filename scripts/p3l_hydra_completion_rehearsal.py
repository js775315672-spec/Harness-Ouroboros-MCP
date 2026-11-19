"""Durable completion admission for a controlled Hydra rehearsal."""
from contextlib import closing
import json
import sqlite3

from p3l_hydra_fast_lane_gate import SHA64, select_lanes


class CompletionRegistry:
    def __init__(self, path, plan, *, approved_tasks=None):
        proposal = select_lanes(plan)
        self.approved_tasks = None
        if approved_tasks is not None:
            known = {task["key"] for task in plan["tasks"]}
            if (type(approved_tasks) not in (list, tuple)
                    or any(type(key) is not str or key not in known for key in approved_tasks)
                    or len(set(approved_tasks)) != len(approved_tasks)):
                raise ValueError("invalid approved task scope")
            self.approved_tasks = tuple(sorted(approved_tasks))
        self.path = path
        with closing(sqlite3.connect(path, timeout=10)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS plan (id INTEGER PRIMARY KEY, sha TEXT, data TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS receipts (run_id INTEGER, job_id INTEGER, "
                       "task TEXT UNIQUE, sha TEXT, PRIMARY KEY (run_id, job_id))")
            db.execute("CREATE TABLE IF NOT EXISTS approval (id INTEGER PRIMARY KEY, scope TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS dispatch_control (id INTEGER PRIMARY KEY, paused INTEGER NOT NULL)")
            db.execute("INSERT OR IGNORE INTO dispatch_control VALUES (1, 0)")
            db.execute("CREATE TABLE IF NOT EXISTS reservations (task TEXT PRIMARY KEY, "
                       "run_id INTEGER, job_id INTEGER)")
            db.execute("CREATE TABLE IF NOT EXISTS starts (task TEXT PRIMARY KEY, "
                       "run_id INTEGER, job_id INTEGER)")
            db.execute("CREATE TABLE IF NOT EXISTS expected_completions (task TEXT PRIMARY KEY, "
                       "run_id INTEGER, job_id INTEGER, UNIQUE (run_id, job_id))")
            db.execute("INSERT OR IGNORE INTO plan VALUES (1, ?, ?)",
                       (proposal["input_sha256"], json.dumps(plan)))
            actual, = db.execute("SELECT sha FROM plan WHERE id=1").fetchone()
            if actual != proposal["input_sha256"]:
                raise ValueError("rehearsal database belongs to a different input plan")
            scope = json.dumps(self.approved_tasks)
            db.execute("INSERT OR IGNORE INTO approval VALUES (1, ?)", (scope,))
            if db.execute("SELECT scope FROM approval WHERE id=1").fetchone() != (scope,):
                raise ValueError("rehearsal database belongs to a different approval scope")

    def set_paused(self, paused):
        if type(paused) is not bool:
            raise ValueError("invalid dispatch pause state")
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("UPDATE dispatch_control SET paused=? WHERE id=1", (paused,))

    @staticmethod
    def _require_dispatch(db):
        if db.execute("SELECT paused FROM dispatch_control WHERE id=1").fetchone() != (0,):
            raise ValueError("Hydra dispatch is paused")

    def _reserve(self, db, plan, event):
        existing = {key for key, in db.execute("SELECT task FROM reservations")}
        view = {**plan, "tasks": [dict(task) for task in plan["tasks"]]}
        for task in view["tasks"]:
            if task["key"] in existing and task["state"] == "pending":
                task["state"] = "running"
            elif task["state"] == "pending" and task["key"] not in self.approved_tasks:
                task["state"] = "blocked"
        capacity = plan["max_parallel"] - sum(task["state"] == "running" for task in view["tasks"])
        if capacity <= 0:
            return []
        view["max_parallel"] = capacity
        reserved = select_lanes(view)["eligible"]
        db.executemany("INSERT INTO reservations VALUES (?, ?, ?)",
                       [(key, event["run_id"], event["job_id"]) for key in reserved])
        return reserved

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
            self._require_dispatch(db)
            raw, = db.execute("SELECT data FROM plan WHERE id=1").fetchone()
            plan = json.loads(raw)
            if event["head"] != plan["head_sha"]:
                raise ValueError("completion HEAD is stale")
            prior = db.execute("SELECT task, sha FROM receipts WHERE run_id=? AND job_id=?",
                               (event["run_id"], event["job_id"])).fetchone()
            if prior is not None:
                if prior != (event["task"], proof["sha256"]):
                    raise ValueError("completion identity already has a different receipt")
                replay = {"accepted": False, "eligible": []}
                if self.approved_tasks is not None:
                    replay["reserved"] = []
                return replay
            task = next((item for item in plan["tasks"] if item["key"] == event["task"]), None)
            expected = db.execute("SELECT run_id, job_id FROM expected_completions WHERE task=?",
                                  (event["task"],)).fetchone()
            from_reserved_worker = (
                task is not None and task["state"] == "pending"
                and expected == (event["run_id"], event["job_id"])
            )
            if task is None or (task["state"] != "running" and not from_reserved_worker):
                raise ValueError("completion does not identify a running task")
            task["state"] = "passed"
            task["evidence_sha"] = proof["sha256"]
            eligible = select_lanes(plan)["eligible"]
            db.execute("INSERT INTO receipts VALUES (?, ?, ?, ?)",
                       (event["run_id"], event["job_id"], event["task"], proof["sha256"]))
            db.execute("UPDATE plan SET data=? WHERE id=1", (json.dumps(plan),))
            result = {"accepted": True, "eligible": eligible}
            if self.approved_tasks is not None:
                result["reserved"] = self._reserve(db, plan, event)
            return result

    def consume(self, task, event, *, observed_head, completion=None):
        """Spend the reserved execution slot before running the isolated task."""
        if (type(task) is not str or type(event) is not dict
                or set(event) != {"task", "head", "run_id", "job_id"}
                or type(observed_head) is not str
                or any(type(event[k]) is not int or not 0 < event[k] <= 2**63-1
                       for k in ("run_id", "job_id"))):
            raise ValueError("invalid execution identity")
        if self.approved_tasks is None or task not in self.approved_tasks:
            raise ValueError("execution task is outside the fixed approval scope")
        if completion is not None and (
            type(completion) is not tuple or len(completion) != 2
            or any(type(value) is not int or not 0 < value <= 2**63-1 for value in completion)
        ):
            raise ValueError("invalid expected worker completion identity")
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._require_dispatch(db)
            raw, = db.execute("SELECT data FROM plan WHERE id=1").fetchone()
            plan = json.loads(raw)
            if observed_head != plan["head_sha"] or event["head"] != observed_head:
                raise ValueError("execution HEAD differs from the reviewed plan")
            origin = (event["run_id"], event["job_id"])
            reservation = db.execute("SELECT run_id, job_id FROM reservations WHERE task=?",
                                     (task,)).fetchone()
            receipt = db.execute("SELECT task FROM receipts WHERE run_id=? AND job_id=?", origin).fetchone()
            if reservation != origin or receipt != (event["task"],):
                raise ValueError("execution does not match a verified reservation")
            started = db.execute("INSERT OR IGNORE INTO starts VALUES (?, ?, ?)",
                                 (task, *origin)).rowcount == 1
            if started and completion is not None:
                already_bound = db.execute("SELECT 1 FROM receipts WHERE run_id=? AND job_id=?",
                                           completion).fetchone()
                if already_bound:
                    raise ValueError("worker completion already belongs to an accepted event")
                db.execute("INSERT INTO expected_completions VALUES (?, ?, ?)", (task, *completion))
            return started
