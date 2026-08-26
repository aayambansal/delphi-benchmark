"""SQLite store for benchmark runs, per-case results, and traces.

Writers are benchmark runners; the dashboard reads. WAL mode so both can
work concurrently.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "runstore.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  created_at REAL NOT NULL,
  finished_at REAL,
  track TEXT NOT NULL,
  system TEXT NOT NULL,
  config TEXT NOT NULL,
  split TEXT NOT NULL,
  status TEXT NOT NULL,
  n_cases INTEGER DEFAULT 0,
  metrics TEXT,
  notes TEXT
);
CREATE TABLE IF NOT EXISTS cases (
  run_id TEXT NOT NULL,
  case_id TEXT NOT NULL,
  workflow TEXT,
  repo TEXT,
  revision TEXT,
  ok INTEGER,
  latency_ms REAL,
  metrics TEXT,
  ranked TEXT,
  gold TEXT,
  trace TEXT,
  created_at REAL,
  PRIMARY KEY (run_id, case_id)
);
CREATE INDEX IF NOT EXISTS idx_cases_run ON cases(run_id);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    return conn


class RunWriter:
    def __init__(
        self,
        *,
        track: str,
        system: str,
        config: dict[str, Any],
        split: str,
        notes: str = "",
        run_id: str | None = None,
    ) -> None:
        self.run_id = run_id or f"{track}-{system}-{time.strftime('%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        self.conn = connect()
        self.conn.execute(
            "INSERT OR REPLACE INTO runs (run_id, created_at, track, system, config, split, status, notes)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (self.run_id, time.time(), track, system, json.dumps(config, sort_keys=True), split, "running", notes),
        )
        self.conn.commit()

    def case(
        self,
        *,
        case_id: str,
        workflow: str | None = None,
        repo: str | None = None,
        revision: str | None = None,
        ok: bool = True,
        latency_ms: float | None = None,
        metrics: dict[str, Any] | None = None,
        ranked: list[str] | None = None,
        gold: list[str] | None = None,
        trace: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO cases (run_id, case_id, workflow, repo, revision, ok, latency_ms,"
            " metrics, ranked, gold, trace, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                self.run_id, case_id, workflow, repo, revision, int(ok), latency_ms,
                json.dumps(metrics or {}, sort_keys=True),
                json.dumps(ranked or []),
                json.dumps(gold or []),
                json.dumps(trace or {}, ensure_ascii=False, default=str),
                time.time(),
            ),
        )
        self.conn.execute(
            "UPDATE runs SET n_cases = (SELECT COUNT(*) FROM cases WHERE run_id=?) WHERE run_id=?",
            (self.run_id, self.run_id),
        )
        self.conn.commit()

    def finish(self, metrics: dict[str, Any], *, status: str = "done") -> None:
        self.conn.execute(
            "UPDATE runs SET finished_at=?, status=?, metrics=? WHERE run_id=?",
            (time.time(), status, json.dumps(metrics, sort_keys=True, default=str), self.run_id),
        )
        self.conn.commit()

    def fail(self, message: str) -> None:
        self.conn.execute(
            "UPDATE runs SET finished_at=?, status='error', notes=? WHERE run_id=?",
            (time.time(), message[:2000], self.run_id),
        )
        self.conn.commit()
