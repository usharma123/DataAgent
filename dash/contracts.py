"""Unified API contracts for Vault — covers both SQL and personal modes."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from dash.personal.contracts import Citation


class VaultAskRequest(BaseModel):
    """Unified request contract for the /v1/ask endpoint."""

    question: str = Field(min_length=1, max_length=3000)
    user_id: str | None = Field(default=None, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)
    include_debug: bool = False
    # Personal-specific (ignored for SQL)
    source_filters: list[str] = Field(default_factory=list)
    time_from: datetime | None = None
    time_to: datetime | None = None
    top_k: int = Field(default=20, ge=1, le=100)
    # SQL-specific (ignored for personal)
    max_sql_attempts: int = Field(default=3, ge=1, le=10)


class VaultAskResponse(BaseModel):
    """Unified response contract for the /v1/ask endpoint."""

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    status: str  # accepted | success | failed
    mode: str  # sql | personal | both
    answer: str | None = None
    # SQL fields (populated when mode=sql)
    sql: str | None = None
    rows: list[dict[str, Any]] | None = None
    # Personal fields (populated when mode=personal)
    citations: list[Citation] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    # Shared
    memory_used: list[str] = Field(default_factory=list)
    error: str | None = None
    debug: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class VaultFeedbackRequest(BaseModel):
    """Unified feedback request routed to the correct store."""

    run_id: str = Field(min_length=1, max_length=64)
    mode: str  # sql | personal
    verdict: str  # correct | incorrect
    comment: str | None = Field(default=None, max_length=4000)
    corrected_answer: str | None = Field(default=None, max_length=4000)
    # SQL-specific
    corrected_sql: str | None = Field(default=None, max_length=20000)
    # Personal-specific
    corrected_filters: list[str] = Field(default_factory=list)
    corrected_source_scope: str | None = Field(default=None, max_length=256)


class VaultFeedbackResponse(BaseModel):
    """Unified feedback acknowledgement."""

    run_id: str
    accepted: bool
    feedback_id: int | None = None
    memory_candidate_ids: list[int] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
