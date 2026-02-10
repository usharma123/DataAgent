"""API contracts for the native Dash runtime."""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


RunStatus = Literal["accepted", "success", "failed"]
FeedbackVerdict = Literal["correct", "incorrect"]


class AskRequest(BaseModel):
    """Request contract for asking a data question."""

    question: str = Field(min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)
    include_debug: bool = False
    max_sql_attempts: int = Field(default=3, ge=1, le=10)


class SqlAttempt(BaseModel):
    """Debug artifact for each SQL attempt in a run."""

    attempt_number: int = Field(ge=1)
    sql: str
    error: str | None = None


class AskResponse(BaseModel):
    """Response contract for an ask run."""

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    status: RunStatus
    answer: str | None = None
    sql: str | None = None
    rows: list[dict[str, Any]] | None = None
    sql_attempts: list[SqlAttempt] | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FeedbackRequest(BaseModel):
    """User feedback contract used by the learning engine."""

    run_id: str = Field(min_length=1, max_length=64)
    verdict: FeedbackVerdict
    comment: str | None = Field(default=None, max_length=4000)
    corrected_answer: str | None = Field(default=None, max_length=4000)
    corrected_sql: str | None = Field(default=None, max_length=20000)


class FeedbackResponse(BaseModel):
    """Acknowledge feedback ingestion."""

    run_id: str
    accepted: bool
    feedback_id: int | None = None
    learning_candidate_id: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SaveQueryRequest(BaseModel):
    """Contract for promoting a validated query into knowledge."""

    name: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=2000)
    query: str = Field(min_length=1, max_length=20000)
    summary: str | None = Field(default=None, max_length=4000)
    tables_used: list[str] = Field(default_factory=list, max_length=30)
    data_quality_notes: str | None = Field(default=None, max_length=4000)


class SaveQueryResponse(BaseModel):
    """Acknowledge save-query requests."""

    query_name: str
    accepted: bool
    query_id: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvalsRunRequest(BaseModel):
    """Contract for running evaluation suites."""

    category: str | None = Field(default=None, max_length=64)
    llm_grader: bool = False
    compare_results: bool = False
    verbose: bool = False


class EvalsRunResponse(BaseModel):
    """Acknowledge eval run requests."""

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    status: RunStatus
    message: str
    total: int | None = None
    passed: int | None = None
    failed: int | None = None
    duration_ms: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
