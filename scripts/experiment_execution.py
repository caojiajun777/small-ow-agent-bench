"""Transactional ownership and append-preserving execution evidence.

Every worker opens the SQLite file belonging to its explicit experiment
context. BEGIN IMMEDIATE serializes admission, retry numbering and claims.
An old heartbeat is a warning, never proof of death or permission to steal.
JSON is a recoverable export of committed DB state, not the ownership lock.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ledger_io import LedgerConflict, process_lock, read_visit, _replace_json


class ExecutionError(RuntimeError):
    pass


class OwnershipError(ExecutionError):
    pass


class AdmissionError(ExecutionError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _money(value, name: str, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite and nonnegative")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return float(value)


def _safe_name(value: str) -> str:
    if not value or value in {".", ".."} or any(c in value for c in '/\\:*?"<>|'):
        raise ValueError("job_name must be one safe filename component")
    if value.rstrip(" .") != value:
        raise ValueError("job_name must not have trailing spaces or dots")
    return value


@dataclass(frozen=True)
class Claim:
    token: str
    slot_id: str
    owner: str
    visit: int
    job_name: str
    model: str | None


class ClaimStore:
    def __init__(self, database: Path, *, manifest_sha256: str | None = None):
        self.path = Path(database).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_sha256 = manifest_sha256
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS visits (
                    token TEXT PRIMARY KEY, slot_id TEXT NOT NULL, owner TEXT NOT NULL,
                    visit INTEGER NOT NULL, job_name TEXT NOT NULL UNIQUE, model TEXT,
                    status TEXT NOT NULL, started_at TEXT NOT NULL, heartbeat_at TEXT NOT NULL,
                    finished_at TEXT, counts_toward_cap INTEGER NOT NULL DEFAULT 1,
                    reserved_usd REAL NOT NULL DEFAULT 0, charged_usd REAL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS visits_slot ON visits(slot_id);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_claim_per_slot
                    ON visits(slot_id) WHERE status = 'running';
                CREATE TABLE IF NOT EXISTS blocked_slots (
                    slot_id TEXT PRIMARY KEY, reason TEXT NOT NULL, evidence TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT,
                    event TEXT NOT NULL, at TEXT NOT NULL, evidence TEXT NOT NULL
                );
            """)
        with self._transaction() as connection:
            row = connection.execute("SELECT value FROM metadata WHERE key='manifest_sha256'").fetchone()
            if row is not None and manifest_sha256 is not None and row[0] != manifest_sha256:
                raise ExecutionError("Claim database belongs to a different frozen manifest")
            if row is None and manifest_sha256 is not None:
                connection.execute("INSERT INTO metadata VALUES ('manifest_sha256', ?)", (manifest_sha256,))

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=30.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA synchronous=FULL")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _transaction(self):
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    @staticmethod
    def _event(connection, token, event, evidence):
        connection.execute(
            "INSERT INTO events(token,event,at,evidence) VALUES (?,?,?,?)",
            (token, event, now_iso(), _json(evidence)),
        )

    @staticmethod
    def _view(row) -> dict:
        value = json.loads(row["payload"])
        value.update({
            "claim_token": row["token"], "slot_id": row["slot_id"], "owner": row["owner"],
            "visit": row["visit"], "job_name": row["job_name"], "status": row["status"],
            "started_at": row["started_at"], "heartbeat_at": row["heartbeat_at"],
            "finished_at": row["finished_at"], "counts_toward_cap": bool(row["counts_toward_cap"]),
            "reserved_usd": row["reserved_usd"], "charged_usd": row["charged_usd"],
        })
        if row["model"] is not None:
            value["model"] = row["model"]
        return value

    def claim(
        self, slot_id: str, owner: str, max_visits: int = 4, *, model: str | None = None,
        serialize_model: bool = False, reserve_usd: float = 3.5,
        budget_usd: float | None = None, max_total_visits: int | None = None,
        job_name: str | None = None,
    ) -> Claim | None:
        if not slot_id or not owner or max_visits < 1:
            raise ValueError("slot_id, owner and positive max_visits are required")
        if serialize_model and not model:
            raise ValueError("serialize_model requires a model identifier")
        reserve = _money(reserve_usd, "reserve_usd")
        budget = _money(budget_usd, "budget_usd", nullable=True)
        with self._transaction() as connection:
            if connection.execute("SELECT 1 FROM blocked_slots WHERE slot_id=?", (slot_id,)).fetchone():
                return None
            if connection.execute(
                "SELECT 1 FROM visits WHERE slot_id=? AND status IN ('scored','running','unknown')", (slot_id,),
            ).fetchone():
                return None
            if serialize_model and connection.execute(
                "SELECT 1 FROM visits WHERE model=? AND status IN ('running','unknown')", (model,),
            ).fetchone():
                return None
            counted = connection.execute(
                "SELECT COUNT(*) FROM visits WHERE slot_id=? AND counts_toward_cap=1", (slot_id,),
            ).fetchone()[0]
            if counted >= max_visits:
                return None
            if max_total_visits is not None:
                total = connection.execute("SELECT COUNT(*) FROM visits WHERE counts_toward_cap=1").fetchone()[0]
                if total >= max_total_visits:
                    raise AdmissionError("Experiment total counted-visit cap exhausted")
            committed = connection.execute(
                "SELECT COALESCE(SUM(COALESCE(charged_usd,reserved_usd)),0) FROM visits",
            ).fetchone()[0]
            if budget is not None and committed + reserve > budget + 1e-12:
                raise AdmissionError("Committed costs/reserves plus this claim exceed the experiment budget")
            number = connection.execute(
                "SELECT COALESCE(MAX(visit),0)+1 FROM visits WHERE slot_id=?", (slot_id,),
            ).fetchone()[0]
            token = uuid.uuid4().hex
            name = _safe_name(job_name or f"visit-{token}")
            stamp = now_iso()
            payload = {"manifest_sha256": self.manifest_sha256}
            connection.execute(
                """INSERT INTO visits(token,slot_id,owner,visit,job_name,model,status,
                       started_at,heartbeat_at,reserved_usd,payload)
                   VALUES (?,?,?,?,?,?,'running',?,?,?,?)""",
                (token, slot_id, owner, number, name, model, stamp, stamp, reserve, _json(payload)),
            )
            self._event(connection, token, "claimed", {"owner": owner, "slot_id": slot_id})
            return Claim(token, slot_id, owner, number, name, model)

    def heartbeat(self, token: str, owner: str) -> bool:
        with self._transaction() as connection:
            return connection.execute(
                "UPDATE visits SET heartbeat_at=? WHERE token=? AND owner=? AND status='running'",
                (now_iso(), token, owner),
            ).rowcount == 1

    def update_running(self, token: str, owner: str, payload: dict) -> dict:
        """Attach child PID/config identity or other live evidence to its owner.

        Operational metadata is persisted before relying on it for recovery;
        callers still need positive liveness/cleanup evidence, not merely a PID.
        """
        if not isinstance(payload, dict):
            raise ValueError("Running metadata must be an object")
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM visits WHERE token=?", (token,)).fetchone()
            if row is None or row["owner"] != owner or row["status"] != "running":
                raise OwnershipError("Running metadata requires the current claim and exact owner")
            value = json.loads(row["payload"])
            value.update(payload)
            if self.manifest_sha256 is not None:
                value["manifest_sha256"] = self.manifest_sha256
            connection.execute(
                "UPDATE visits SET payload=?,heartbeat_at=? WHERE token=?",
                (_json(value), now_iso(), token),
            )
            self._event(connection, token, "running_metadata", {"keys": sorted(payload)})
            return self._view(connection.execute("SELECT * FROM visits WHERE token=?", (token,)).fetchone())

    def complete(
        self, token: str, owner: str, status: str, payload: dict, *,
        counts_toward_cap: bool = True, charged_usd: float | None = None,
    ) -> dict:
        if status not in {"scored", "infra", "aborted"}:
            raise ValueError("Terminal status must be scored, infra or aborted")
        if not isinstance(payload, dict):
            raise ValueError("Completion payload must be an object")
        cost = _money(charged_usd, "charged_usd", nullable=True)
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM visits WHERE token=?", (token,)).fetchone()
            if row is None or row["owner"] != owner or row["status"] != "running":
                raise OwnershipError("Completion requires the current running claim and exact owner")
            value = json.loads(row["payload"])
            value.update(payload)
            if self.manifest_sha256 is not None:
                value["manifest_sha256"] = self.manifest_sha256
            stamp = now_iso()
            connection.execute(
                """UPDATE visits SET status=?,finished_at=?,heartbeat_at=?,payload=?,
                    counts_toward_cap=?,charged_usd=? WHERE token=?""",
                (status, stamp, stamp, _json(value), int(counts_toward_cap), cost, token),
            )
            self._event(connection, token, "completed", {"status": status, "owner": owner})
            return self._view(connection.execute("SELECT * FROM visits WHERE token=?", (token,)).fetchone())

    def abort(self, token: str, owner: str, reason: str, *, evidence: dict) -> dict:
        if evidence.get("execution_stopped") is not True:
            raise OwnershipError("Abort needs affirmative execution_stopped evidence")
        return self.complete(token, owner, "aborted", {"reason": reason, "recovery_evidence": evidence})

    def recover_orphan(self, token: str, evidence: dict) -> dict:
        """Administrative recovery after positive process AND sandbox checks.

        No expiry/age-only takeover. Missing billing remains unknown, and the
        attempt remains cap-counted unless separately adjudicated with evidence.
        """
        if not all(evidence.get(k) is True for k in ("process_terminated", "sandbox_cleanup_confirmed")):
            raise OwnershipError("Recovery needs confirmed process termination and sandbox cleanup")
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM visits WHERE token=?", (token,)).fetchone()
            if row is None or row["status"] not in {"running", "unknown"}:
                raise OwnershipError("Only an unresolved claim can be recovered")
            value = json.loads(row["payload"])
            value["recovery_evidence"] = evidence
            connection.execute(
                "UPDATE visits SET status='infra',finished_at=?,payload=? WHERE token=?",
                (now_iso(), _json(value), token),
            )
            self._event(connection, token, "orphan_recovered", evidence)
            return self._view(connection.execute("SELECT * FROM visits WHERE token=?", (token,)).fetchone())

    def records(self) -> list[dict]:
        with self._connect() as connection:
            return [self._view(r) for r in connection.execute("SELECT * FROM visits ORDER BY started_at,token")]

    def active_claims(self) -> list[dict]:
        return [v for v in self.records() if v["status"] in {"running", "unknown"}]

    def blocked_slots(self) -> list[dict]:
        with self._connect() as connection:
            return [dict(r) for r in connection.execute("SELECT * FROM blocked_slots ORDER BY slot_id")]

    def import_visits(self, rows: list[dict]) -> dict:
        """Import legacy evidence once; never overwrite its JSON or DB terminal.

        Existing scored records block a new claim. Ambiguous duplicates and
        unknown statuses quarantine their slot. Imported running records remain
        unresolved until explicit recovery, not silently reaped by age.
        """
        imported = 0
        with self._transaction() as connection:
            for value in rows:
                if not isinstance(value, dict) or not value.get("job_name") or not value.get("slot_id"):
                    raise ExecutionError("Cannot import a malformed visit; repair/quarantine evidence explicitly")
                name = _safe_name(value["job_name"])
                existing = connection.execute("SELECT * FROM visits WHERE job_name=?", (name,)).fetchone()
                if existing is not None:
                    # Do not replay a stale JSON snapshot over authoritative DB state.
                    continue
                status = value.get("status", "unknown")
                if status not in {"scored", "running", "infra", "aborted"}:
                    status = "unknown"
                # Two imported running records for one slot cannot coexist under
                # the unique active-slot index; retain the second as unknown.
                if status == "running" and connection.execute(
                    "SELECT 1 FROM visits WHERE slot_id=? AND status='running'", (value["slot_id"],),
                ).fetchone():
                    status = "unknown"
                token = "import-" + hashlib.sha256(name.encode()).hexdigest()
                number = value.get("visit", 1)
                if isinstance(number, bool) or not isinstance(number, int) or number < 1:
                    raise ExecutionError("Imported visit number must be a positive integer")
                stamp = value.get("started_at") or now_iso()
                connection.execute(
                    """INSERT INTO visits(token,slot_id,owner,visit,job_name,model,status,
                        started_at,heartbeat_at,finished_at,counts_toward_cap,reserved_usd,charged_usd,payload)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (token, value["slot_id"], value.get("owner") or "legacy-import", number, name,
                     value.get("model"), status, stamp, value.get("heartbeat_at") or stamp,
                     value.get("finished_at"), int(value.get("counts_toward_cap", True)),
                     _money(value.get("reserved_usd", 3.5), "reserved_usd"),
                     _money(value.get("charged_usd"), "charged_usd", nullable=True), _json(value)),
                )
                self._event(connection, token, "legacy_imported", {"job_name": name})
                imported += 1
            duplicate_rows = connection.execute(
                "SELECT slot_id,visit,COUNT(*) AS n FROM visits GROUP BY slot_id,visit HAVING COUNT(*)>1",
            ).fetchall()
            duplicate_scored = connection.execute(
                "SELECT slot_id,COUNT(*) AS n FROM visits WHERE status='scored' GROUP BY slot_id HAVING COUNT(*)>1",
            ).fetchall()
            unknown = connection.execute("SELECT slot_id,job_name FROM visits WHERE status='unknown'").fetchall()
            for row in [*duplicate_rows, *duplicate_scored, *unknown]:
                connection.execute(
                    "INSERT OR IGNORE INTO blocked_slots VALUES (?,?,?)",
                    (row["slot_id"], "ambiguous imported evidence", _json(dict(row))),
                )
        return {"imported": imported, "blocked_slots": self.blocked_slots()}

    def publish_visit(self, claim_or_token: Claim | str, visits_dir: Path) -> Path:
        """Export committed evidence without replacing an existing terminal.

        A crash between DB commit and export is repaired by calling this again.
        Only this exact claim's running export may be advanced to its terminal;
        legacy evidence and mismatched owner/token are never overwritten.
        """
        token = claim_or_token.token if isinstance(claim_or_token, Claim) else claim_or_token
        # Hold the DB write transaction through export: a competing completion
        # cannot commit between our read and publishing an obsolete running view.
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM visits WHERE token=?", (token,)).fetchone()
            if row is None:
                raise OwnershipError("Unknown claim")
            value = self._view(row)
            path = Path(visits_dir) / f"{_safe_name(value['job_name'])}.json"
            with process_lock(path):
                current = read_visit(path)
                if path.exists():
                    if current == value:
                        return path
                    if (current is None or current.get("claim_token") != token
                            or current.get("owner") != value["owner"]
                            or current.get("status") != "running"):
                        raise LedgerConflict("Existing evidence is immutable or belongs to a different claim")
                _replace_json(path, value)
        return path
