from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from ecom_insight.api.schemas import FeedbackCreate, FeedbackRecord


class FeedbackStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS attribution_feedback (
                    feedback_id TEXT PRIMARY KEY,
                    attribution_id TEXT NOT NULL,
                    decision TEXT NOT NULL CHECK (
                        decision IN ('accepted', 'rejected', 'corrected')
                    ),
                    corrected_cause_code TEXT,
                    notes TEXT,
                    reviewer_alias TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_feedback_attribution
                ON attribution_feedback(attribution_id, created_at DESC)
                """
            )

    def ready(self) -> bool:
        return self.database_path.is_file()

    def create(
        self,
        *,
        attribution_id: str,
        payload: FeedbackCreate,
    ) -> FeedbackRecord:
        if payload.decision == "corrected" and not payload.corrected_cause_code:
            raise ValueError("corrected decision requires corrected_cause_code")
        created_at = datetime.now(UTC)
        feedback_id = uuid.uuid4().hex
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO attribution_feedback VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_id,
                    attribution_id,
                    payload.decision,
                    payload.corrected_cause_code,
                    payload.notes,
                    payload.reviewer_alias,
                    created_at.isoformat(),
                ),
            )
        return FeedbackRecord(
            feedback_id=feedback_id,
            attribution_id=attribution_id,
            decision=payload.decision,
            corrected_cause_code=payload.corrected_cause_code,
            notes=payload.notes,
            reviewer_alias=payload.reviewer_alias,
            created_at=created_at,
        )

    def list_for_attribution(self, attribution_id: str) -> list[FeedbackRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM attribution_feedback
                WHERE attribution_id = ?
                ORDER BY created_at DESC
                """,
                (attribution_id,),
            ).fetchall()
        return [
            FeedbackRecord(
                feedback_id=str(row["feedback_id"]),
                attribution_id=str(row["attribution_id"]),
                decision=str(row["decision"]),  # type: ignore[arg-type]
                corrected_cause_code=(
                    str(row["corrected_cause_code"])
                    if row["corrected_cause_code"] is not None
                    else None
                ),
                notes=str(row["notes"]) if row["notes"] is not None else None,
                reviewer_alias=(
                    str(row["reviewer_alias"])
                    if row["reviewer_alias"] is not None
                    else None
                ),
                created_at=datetime.fromisoformat(str(row["created_at"])),
            )
            for row in rows
        ]

