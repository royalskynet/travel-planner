"""Small SQLite revision repository with JSON domain snapshots."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from travel_assistant.domain import Trip


@dataclass(frozen=True)
class RevisionRecord:
    trip_id: str
    revision: int
    trip: Trip
    created_at: datetime
    plan: Optional[Dict[str, Any]]
    provider_summary: Optional[Dict[str, Any]]


class SQLiteTripRepository:
    """Append-only trip snapshots; each save creates one atomic revision."""

    def __init__(self, database: Union[str, Path]) -> None:
        self.database = str(database)
        if self.database != ":memory:":
            path = Path(self.database).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            self.database = str(path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise RuntimeError(f"database schema {version} is newer than supported schema 1")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS trip_revisions (
                    trip_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision > 0),
                    created_at TEXT NOT NULL,
                    trip_json TEXT NOT NULL,
                    plan_json TEXT,
                    provider_summary_json TEXT,
                    PRIMARY KEY (trip_id, revision)
                );
                CREATE INDEX IF NOT EXISTS idx_trip_revisions_latest
                    ON trip_revisions (trip_id, revision DESC);
                PRAGMA user_version = 1;
                """
            )

    def save(
        self,
        trip: Trip,
        *,
        plan: Optional[Dict[str, Any]] = None,
        provider_summary: Optional[Dict[str, Any]] = None,
    ) -> int:
        trip_json = json.dumps(trip.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        plan_json = None if plan is None else json.dumps(plan, ensure_ascii=False, sort_keys=True)
        provider_json = None if provider_summary is None else json.dumps(provider_summary, ensure_ascii=False, sort_keys=True)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT COALESCE(MAX(revision), 0) + 1 FROM trip_revisions WHERE trip_id = ?",
                (trip.id,),
            ).fetchone()
            revision = int(row[0])
            connection.execute(
                """INSERT INTO trip_revisions
                   (trip_id, revision, created_at, trip_json, plan_json, provider_summary_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (trip.id, revision, now, trip_json, plan_json, provider_json),
            )
        return revision

    def get(self, trip_id: str, revision: Optional[int] = None) -> RevisionRecord:
        query = "SELECT * FROM trip_revisions WHERE trip_id = ?"
        parameters: tuple[Any, ...] = (trip_id,)
        if revision is None:
            query += " ORDER BY revision DESC LIMIT 1"
        else:
            query += " AND revision = ?"
            parameters = (trip_id, revision)
        with self._connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        if row is None:
            label = "latest" if revision is None else str(revision)
            raise KeyError(f"trip {trip_id!r} revision {label} not found")
        return self._decode(row)

    def get_latest_planned(self, trip_id: str) -> RevisionRecord:
        """Return the newest revision containing a generated plan."""

        with self._connect() as connection:
            row = connection.execute(
                """SELECT * FROM trip_revisions
                   WHERE trip_id = ? AND plan_json IS NOT NULL
                   ORDER BY revision DESC LIMIT 1""",
                (trip_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"trip {trip_id!r} has no planned revision")
        return self._decode(row)

    def list_revisions(self, trip_id: str) -> List[int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT revision FROM trip_revisions WHERE trip_id = ? ORDER BY revision",
                (trip_id,),
            ).fetchall()
        return [int(row[0]) for row in rows]

    @staticmethod
    def _decode(row: sqlite3.Row) -> RevisionRecord:
        return RevisionRecord(
            trip_id=row["trip_id"],
            revision=int(row["revision"]),
            trip=Trip.model_validate_json(row["trip_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            plan=None if row["plan_json"] is None else json.loads(row["plan_json"]),
            provider_summary=None if row["provider_summary_json"] is None else json.loads(row["provider_summary_json"]),
        )
