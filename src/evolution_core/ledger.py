"""Per-agent append-only logical SQLite evidence ledger with hash verification.

SQLite file owners can rewrite history; a remote signed checkpoint is still P1.
"""
from dataclasses import asdict
from hashlib import sha256
import json
import sqlite3
from pathlib import Path
from .contracts import AgentID, EvidenceRecord

def canon(payload) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)

class Ledger:
    def __init__(self, path: str | Path, agent_id: AgentID):
        self.path = str(path)
        self.agent_id = agent_id
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS identity (only_row INTEGER PRIMARY KEY CHECK(only_row=1), agent TEXT NOT NULL)")
            db.execute("INSERT OR IGNORE INTO identity VALUES (1, ?)", (agent_id.value,))
            if db.execute("SELECT agent FROM identity WHERE only_row=1").fetchone()[0] != agent_id.value:
                raise PermissionError("cross-agent ledger access")
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id TEXT NOT NULL, run_url TEXT NOT NULL,
                payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                previous_event_sha256 TEXT NOT NULL, event_sha256 TEXT NOT NULL,
                UNIQUE(experiment_id, run_url, payload_sha256)
            )""")
            db.execute("""CREATE TRIGGER IF NOT EXISTS forbid_event_update
                BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'append only'); END""")
            db.execute("""CREATE TRIGGER IF NOT EXISTS forbid_event_delete
                BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'append only'); END""")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=15)

    def _verify(self, db) -> bool:
        prev = "0" * 64
        for event_id, payload, payload_sha, prev_in_row, chain_hash in db.execute(
            "SELECT event_id,payload,payload_sha256,previous_event_sha256,event_sha256 FROM events ORDER BY event_id"
        ):
            if sha256(payload.encode("utf-8")).hexdigest() != payload_sha or prev != prev_in_row:
                return False
            expected = sha256(canon({"event_id": event_id, "agent": self.agent_id.value,
                                      "payload_sha256": payload_sha, "previous_event_sha256": prev}).encode()).hexdigest()
            if chain_hash != expected:
                return False
            prev = chain_hash
        return True

    def append(self, record: EvidenceRecord) -> None:
        if record.agent_id != self.agent_id:
            raise PermissionError("cross-agent evidence append")
        payload = canon(asdict(record))
        digest = sha256(payload.encode("utf-8")).hexdigest()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not self._verify(db):
                raise ValueError("ledger chain tampered")
            latest = db.execute("SELECT event_sha256 FROM events ORDER BY event_id DESC LIMIT 1").fetchone()
            prev = latest[0] if latest else "0" * 64
            row = db.execute("SELECT COALESCE(MAX(event_id),0)+1 FROM events").fetchone()[0]
            event_hash = sha256(canon({"event_id": row, "agent": self.agent_id.value,
                                      "payload_sha256": digest, "previous_event_sha256": prev}).encode()).hexdigest()
            db.execute("INSERT INTO events(event_id,experiment_id,run_url,payload,payload_sha256,previous_event_sha256,event_sha256) VALUES(?,?,?,?,?,?,?)",
                       (row, record.experiment_id, record.run_url, payload, digest, prev, event_hash))

    def verify_chain(self) -> bool:
        with self._connect() as db:
            return self._verify(db)

    def export_jsonl(self) -> str:
        if not self.verify_chain():
            raise ValueError("ledger chain tampered")
        with self._connect() as db:
            rows = db.execute("SELECT event_id,payload_sha256,previous_event_sha256,event_sha256 FROM events ORDER BY event_id")
            return "".join(canon(dict(event_id=r[0], agent_id=self.agent_id.value,
                                      payload_sha256=r[1], previous_event_sha256=r[2], event_sha256=r[3])) + "\n"
                           for r in rows)
