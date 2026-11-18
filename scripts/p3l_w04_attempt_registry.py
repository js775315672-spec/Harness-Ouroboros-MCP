"""Durable one-call reservation for workers using the same local SQLite file."""
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
import re
import sqlite3
import time

from resumable_task_queue import canonical, fingerprint

SHA40 = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")


@dataclass(frozen=True)
class AttemptInput:
    task_type: str
    public_contract_sha256: str
    base_sha: str
    head_sha: str
    model_revision: str
    gguf_sha256: str
    inference_config_sha256: str
    prompt_sha256: str

    def __post_init__(self):
        if type(self.task_type) is not str or not IDENTIFIER.fullmatch(self.task_type):
            raise ValueError("invalid task type")
        for value in (self.base_sha, self.head_sha, self.model_revision):
            if type(value) is not str or not SHA40.fullmatch(value):
                raise ValueError("invalid Git or model revision")
        for value in (self.public_contract_sha256, self.gguf_sha256,
                      self.inference_config_sha256, self.prompt_sha256):
            if type(value) is not str or not SHA256.fullmatch(value):
                raise ValueError("invalid immutable input digest")

    @property
    def semantic_key(self):
        return fingerprint({"task_type": self.task_type,
                            "public_contract_sha256": self.public_contract_sha256})

    @property
    def task_key(self):
        return fingerprint({**asdict(self), "attempt_index": 1})


@dataclass(frozen=True)
class Lease:
    task_key: str
    owner: str
    epoch: int
    expires_at: int

    def __post_init__(self):
        if (type(self.task_key) is not str or not SHA256.fullmatch(self.task_key)
                or type(self.owner) is not str or not IDENTIFIER.fullmatch(self.owner)
                or type(self.epoch) is not int or self.epoch < 1
                or type(self.expires_at) is not int or self.expires_at < 1):
            raise ValueError("invalid lease identity")


class AttemptBlocked(ValueError):
    """No model execution authority was granted."""


class AttemptRegistry:
    def __init__(self, path, *, clock=time.time):
        self.path = Path(path).absolute()
        self.clock = clock
        with self._transaction() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS attempts (
                    semantic_key TEXT PRIMARY KEY,
                    task_key TEXT UNIQUE NOT NULL,
                    input_json TEXT NOT NULL,
                    expected_head TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    epoch INTEGER NOT NULL CHECK (epoch >= 1),
                    heartbeat_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('LEASED', 'STARTED', 'MODEL_GENERATED')),
                    run_id INTEGER CHECK (run_id > 0),
                    receipt_sha256 TEXT,
                    CHECK (
                        (state = 'LEASED' AND run_id IS NULL AND receipt_sha256 IS NULL)
                        OR (state = 'STARTED' AND run_id IS NOT NULL AND receipt_sha256 IS NULL)
                        OR (state = 'MODEL_GENERATED' AND run_id IS NOT NULL AND receipt_sha256 IS NOT NULL)
                    )
                )
            """)

    @contextmanager
    def _transaction(self):
        if self.path.is_symlink():
            raise ValueError("registry path must be a local database file")
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            yield db

    def reserve(self, inputs, owner, *, ttl_seconds):
        if type(owner) is not str or not IDENTIFIER.fullmatch(owner):
            raise ValueError("invalid lease owner")
        if type(ttl_seconds) is not int or ttl_seconds < 1:
            raise ValueError("lease TTL must be a positive integer")
        semantic_key, task_key = inputs.semantic_key, inputs.task_key
        payload = canonical(asdict(inputs)).decode("utf-8")
        with self._transaction() as db:
            now = int(self.clock())
            result = db.execute("""
                INSERT INTO attempts (
                    semantic_key, task_key, input_json, expected_head, owner, epoch,
                    heartbeat_at, expires_at, state
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, 'LEASED')
                ON CONFLICT(semantic_key) DO UPDATE SET
                    task_key = excluded.task_key, input_json = excluded.input_json,
                    expected_head = excluded.expected_head, owner = excluded.owner,
                    epoch = attempts.epoch + 1, heartbeat_at = excluded.heartbeat_at,
                    expires_at = excluded.expires_at
                WHERE attempts.state = 'LEASED' AND attempts.expires_at <= excluded.heartbeat_at
            """, (semantic_key, task_key, payload, inputs.head_sha, owner, now, now + ttl_seconds))
            if result.rowcount != 1:
                raise AttemptBlocked("task already leased or its model budget is consumed")
            epoch = db.execute("SELECT epoch FROM attempts WHERE semantic_key = ?",
                               (semantic_key,)).fetchone()["epoch"]
            return Lease(task_key, owner, epoch, now + ttl_seconds)

    def heartbeat(self, lease, *, ttl_seconds):
        if type(ttl_seconds) is not int or ttl_seconds < 1:
            raise ValueError("lease TTL must be a positive integer")
        with self._transaction() as db:
            now = int(self.clock())
            result = db.execute("""
                UPDATE attempts SET heartbeat_at = ?, expires_at = ?
                WHERE task_key = ? AND owner = ? AND epoch = ? AND expires_at > ?
                    AND state IN ('LEASED', 'STARTED')
            """, (now, now + ttl_seconds, lease.task_key, lease.owner, lease.epoch, now))
            if result.rowcount != 1:
                raise AttemptBlocked("cannot renew a stale or expired lease")
            return Lease(lease.task_key, lease.owner, lease.epoch, now + ttl_seconds)

    def start(self, lease, *, observed_head, run_id):
        """Spend the one-call budget durably before the caller invokes a model."""
        if type(run_id) is not int or not 0 < run_id <= 2**63 - 1:
            raise ValueError("invalid run id")
        with self._transaction() as db:
            result = db.execute("""
                UPDATE attempts SET state = 'STARTED', run_id = ?
                WHERE task_key = ? AND owner = ? AND epoch = ? AND expected_head = ?
                    AND expires_at > ? AND state = 'LEASED'
            """, (run_id, lease.task_key, lease.owner, lease.epoch, observed_head, int(self.clock())))
            if result.rowcount != 1:
                raise AttemptBlocked("stale lease, wrong HEAD, or model budget already consumed")

    def record_model_generated(self, lease, *, run_id, receipt_sha256):
        """Record an artifact receipt idempotently, including after lease expiry."""
        if type(run_id) is not int or not 0 < run_id <= 2**63 - 1:
            raise ValueError("invalid run id")
        if type(receipt_sha256) is not str or not SHA256.fullmatch(receipt_sha256):
            raise ValueError("invalid model receipt digest")
        with self._transaction() as db:
            result = db.execute("""
                UPDATE attempts SET state = 'MODEL_GENERATED', receipt_sha256 = ?
                WHERE task_key = ? AND owner = ? AND epoch = ? AND run_id = ?
                    AND (state = 'STARTED' OR (state = 'MODEL_GENERATED' AND receipt_sha256 = ?))
            """, (receipt_sha256, lease.task_key, lease.owner, lease.epoch, run_id, receipt_sha256))
            if result.rowcount != 1:
                raise AttemptBlocked("receipt conflicts with the admitted run")

    def status(self, inputs):
        """Return the stored task record or the fail-closed view of an expired run."""
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM attempts WHERE semantic_key = ?",
                             (inputs.semantic_key,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        if row["expires_at"] <= int(self.clock()):
            if row["state"] == "STARTED":
                result["state"] = "UNVERIFIED"
            elif row["state"] == "LEASED":
                result["state"] = "EXPIRED"
        return result
