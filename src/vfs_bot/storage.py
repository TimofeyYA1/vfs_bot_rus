from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import CheckState, SlotObservation, StateChange


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS target_state (
                    target_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    details TEXT NOT NULL
                )
                """
            )

    def update(self, observation: SlotObservation) -> StateChange:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state, fingerprint FROM target_state WHERE target_id = ?",
                (observation.target_id,),
            ).fetchone()

            previous_state = CheckState(row["state"]) if row else None
            previous_fingerprint = row["fingerprint"] if row else None

            connection.execute(
                """
                INSERT INTO target_state(target_id, state, fingerprint, checked_at, details)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(target_id) DO UPDATE SET
                    state = excluded.state,
                    fingerprint = excluded.fingerprint,
                    checked_at = excluded.checked_at,
                    details = excluded.details
                """,
                (
                    observation.target_id,
                    observation.state.value,
                    observation.fingerprint,
                    observation.checked_at.isoformat(),
                    observation.details,
                ),
            )

        return StateChange(
            previous_state=previous_state,
            state_changed=previous_state != observation.state,
            fingerprint_changed=previous_fingerprint != observation.fingerprint,
        )

    def snapshot(self) -> dict[str, CheckState]:
        with self._connect() as connection:
            rows = connection.execute("SELECT target_id, state FROM target_state").fetchall()
        return {row["target_id"]: CheckState(row["state"]) for row in rows}
