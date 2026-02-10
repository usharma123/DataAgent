"""Persistence layer for native Dash runs."""

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    select,
)
from sqlalchemy.exc import SQLAlchemyError


metadata = MetaData()

query_runs = Table(
    "query_runs",
    metadata,
    # Shared run id used across API, logs, and future async workers.
    Column("run_id", String(64), primary_key=True),
    Column("status", String(16), nullable=False),
    Column("question", Text, nullable=False),
    Column("user_id", String(128), nullable=True),
    Column("session_id", String(128), nullable=True),
    Column("max_sql_attempts", Integer, nullable=False),
    Column("answer", Text, nullable=True),
    Column("error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

sql_attempts = Table(
    "sql_attempts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "run_id",
        String(64),
        ForeignKey("query_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("attempt_number", Integer, nullable=False),
    Column("sql", Text, nullable=False),
    Column("error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

feedback_events = Table(
    "feedback_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(64), nullable=False),
    Column("verdict", String(16), nullable=False),
    Column("comment", Text, nullable=True),
    Column("corrected_answer", Text, nullable=True),
    Column("corrected_sql", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

learning_candidates = Table(
    "learning_candidates",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(64), nullable=True),
    Column("source", String(32), nullable=False),
    Column("title", String(255), nullable=False),
    Column("learning", Text, nullable=False),
    Column("confidence", Integer, nullable=False),
    Column("status", String(32), nullable=False),
    Column("metadata_json", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

validated_queries = Table(
    "validated_queries",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(128), nullable=False),
    Column("question", Text, nullable=False),
    Column("query", Text, nullable=False),
    Column("summary", Text, nullable=True),
    Column("tables_used_json", Text, nullable=True),
    Column("data_quality_notes", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

eval_runs = Table(
    "eval_runs",
    metadata,
    Column("run_id", String(64), primary_key=True),
    Column("status", String(16), nullable=False),
    Column("summary", Text, nullable=False),
    Column("results_json", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


class NativeRunStoreError(RuntimeError):
    """Storage operation failed."""


class NativeRunStore:
    """Run store for native orchestrator state and SQL attempt logs."""

    def __init__(self, database_url: str):
        self._engine = create_engine(database_url, pool_pre_ping=True)
        self._schema_ready = False

    def ensure_schema(self) -> None:
        """Create native run logging tables if needed."""
        if self._schema_ready:
            return
        try:
            metadata.create_all(self._engine, checkfirst=True)
            self._schema_ready = True
        except SQLAlchemyError as exc:
            raise NativeRunStoreError(f"Failed to create native tables: {exc}") from exc

    def create_query_run(
        self,
        *,
        run_id: str,
        status: str,
        question: str,
        user_id: str | None,
        session_id: str | None,
        max_sql_attempts: int,
    ) -> None:
        """Insert a new run row."""
        self.ensure_schema()
        now = datetime.now(UTC)
        payload = {
            "run_id": run_id,
            "status": status,
            "question": question,
            "user_id": user_id,
            "session_id": session_id,
            "max_sql_attempts": max_sql_attempts,
            "created_at": now,
            "updated_at": now,
        }
        try:
            with self._engine.begin() as conn:
                conn.execute(query_runs.insert().values(**payload))
        except SQLAlchemyError as exc:
            raise NativeRunStoreError(f"Failed to create query run: {exc}") from exc

    def update_query_run(
        self,
        *,
        run_id: str,
        status: str,
        answer: str | None = None,
        error: str | None = None,
    ) -> None:
        """Update run status and terminal metadata."""
        self.ensure_schema()
        values: dict[str, Any] = {"status": status, "updated_at": datetime.now(UTC)}
        if answer is not None:
            values["answer"] = answer
        if error is not None:
            values["error"] = error
        try:
            with self._engine.begin() as conn:
                result = conn.execute(
                    query_runs.update().where(query_runs.c.run_id == run_id).values(**values)
                )
                if result.rowcount == 0:
                    raise NativeRunStoreError(f"Run {run_id} not found for update")
        except SQLAlchemyError as exc:
            raise NativeRunStoreError(f"Failed to update query run: {exc}") from exc

    def log_sql_attempt(
        self,
        *,
        run_id: str,
        attempt_number: int,
        sql: str,
        error: str | None = None,
    ) -> None:
        """Insert one SQL attempt record for a run."""
        self.ensure_schema()
        payload = {
            "run_id": run_id,
            "attempt_number": attempt_number,
            "sql": sql,
            "error": error,
            "created_at": datetime.now(UTC),
        }
        try:
            with self._engine.begin() as conn:
                conn.execute(sql_attempts.insert().values(**payload))
        except SQLAlchemyError as exc:
            raise NativeRunStoreError(f"Failed to log SQL attempt: {exc}") from exc

    def list_sql_attempts(self, *, run_id: str) -> list[dict[str, Any]]:
        """Return SQL attempts for a run, ordered by attempt number."""
        self.ensure_schema()
        stmt = (
            select(sql_attempts.c.attempt_number, sql_attempts.c.sql, sql_attempts.c.error)
            .where(sql_attempts.c.run_id == run_id)
            .order_by(sql_attempts.c.attempt_number.asc())
        )
        try:
            with self._engine.begin() as conn:
                rows = conn.execute(stmt).mappings().all()
            return [dict(row) for row in rows]
        except SQLAlchemyError as exc:
            raise NativeRunStoreError(f"Failed to read SQL attempts: {exc}") from exc

    def create_feedback_event(
        self,
        *,
        run_id: str,
        verdict: str,
        comment: str | None,
        corrected_answer: str | None,
        corrected_sql: str | None,
    ) -> int:
        """Persist user feedback and return feedback event id."""
        self.ensure_schema()
        payload = {
            "run_id": run_id,
            "verdict": verdict,
            "comment": comment,
            "corrected_answer": corrected_answer,
            "corrected_sql": corrected_sql,
            "created_at": datetime.now(UTC),
        }
        try:
            with self._engine.begin() as conn:
                result = conn.execute(feedback_events.insert().values(**payload))
                return int(result.inserted_primary_key[0])
        except (SQLAlchemyError, ValueError, TypeError) as exc:
            raise NativeRunStoreError(f"Failed to save feedback event: {exc}") from exc

    def create_learning_candidate(
        self,
        *,
        run_id: str | None,
        source: str,
        title: str,
        learning: str,
        confidence: int,
        status: str = "new",
        metadata_dict: dict[str, Any] | None = None,
    ) -> int:
        """Persist a learning candidate and return id."""
        self.ensure_schema()
        payload = {
            "run_id": run_id,
            "source": source,
            "title": title,
            "learning": learning,
            "confidence": confidence,
            "status": status,
            "metadata_json": json.dumps(metadata_dict) if metadata_dict else None,
            "created_at": datetime.now(UTC),
        }
        try:
            with self._engine.begin() as conn:
                result = conn.execute(learning_candidates.insert().values(**payload))
                return int(result.inserted_primary_key[0])
        except (SQLAlchemyError, ValueError, TypeError) as exc:
            raise NativeRunStoreError(f"Failed to save learning candidate: {exc}") from exc

    def save_validated_query(
        self,
        *,
        name: str,
        question: str,
        query: str,
        summary: str | None,
        tables_used: list[str],
        data_quality_notes: str | None,
    ) -> int:
        """Persist a validated query and return id."""
        self.ensure_schema()
        payload = {
            "name": name,
            "question": question,
            "query": query,
            "summary": summary,
            "tables_used_json": json.dumps(tables_used),
            "data_quality_notes": data_quality_notes,
            "created_at": datetime.now(UTC),
        }
        try:
            with self._engine.begin() as conn:
                result = conn.execute(validated_queries.insert().values(**payload))
                return int(result.inserted_primary_key[0])
        except (SQLAlchemyError, ValueError, TypeError) as exc:
            raise NativeRunStoreError(f"Failed to save validated query: {exc}") from exc

    def create_eval_run(
        self,
        *,
        run_id: str,
        status: str,
        summary: str,
        results: dict[str, Any],
    ) -> None:
        """Persist an evaluation run summary."""
        self.ensure_schema()
        payload = {
            "run_id": run_id,
            "status": status,
            "summary": summary,
            "results_json": json.dumps(results),
            "created_at": datetime.now(UTC),
        }
        try:
            with self._engine.begin() as conn:
                conn.execute(eval_runs.insert().values(**payload))
        except (SQLAlchemyError, ValueError, TypeError) as exc:
            raise NativeRunStoreError(f"Failed to save eval run: {exc}") from exc
