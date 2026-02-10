"""API contracts for personal data agent runtime."""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


PersonalSource = Literal["gmail", "slack", "imessage", "files"]
RunStatus = Literal["accepted", "success", "failed"]
FeedbackVerdict = Literal["correct", "incorrect"]
MemoryKind = Literal["UserPreference", "SourceQuirk", "ReasoningRule", "GuardrailException"]
MemoryScope = Literal["session", "user-global", "source-specific"]
MemoryCandidateStatus = Literal["proposed", "approved", "rejected"]
MemoryActivationState = Literal["active", "stale", "deprecated"]


class Citation(BaseModel):
    """Citation to an evidence chunk used in response."""

    citation_id: str
    source: PersonalSource
    title: str | None = None
    snippet: str
    author: str | None = None
    timestamp: datetime | None = None
    deep_link: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class AskDebug(BaseModel):
    """Debug details for personal ask runs."""

    memory_used: list[str] = Field(default_factory=list)
    memory_skipped: list[str] = Field(default_factory=list)


class PersonalAskRequest(BaseModel):
    """Request contract for personal ask endpoint."""

    question: str = Field(min_length=1, max_length=3000)
    user_id: str | None = Field(default=None, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)
    source_filters: list[PersonalSource] = Field(default_factory=list)
    time_from: datetime | None = None
    time_to: datetime | None = None
    top_k: int = Field(default=20, ge=1, le=100)
    include_debug: bool = False


class PersonalAskResponse(BaseModel):
    """Response contract for personal ask endpoint."""

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    status: RunStatus
    answer: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    debug: AskDebug | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SourceStatus(BaseModel):
    """Current status of one configured source."""

    source: PersonalSource
    connected: bool
    last_sync_at: datetime | None = None
    cursor: dict[str, Any] | None = None


class SourceStatusResponse(BaseModel):
    """Response payload for listing source status."""

    sources: list[SourceStatus]


class ConnectSourceRequest(BaseModel):
    """Connect source request payload."""

    cursor: dict[str, Any] | None = None


class SyncSourceRequest(BaseModel):
    """Sync source request payload."""

    full: bool = False


class SyncSourceResponse(BaseModel):
    """Source sync result."""

    source: PersonalSource
    accepted: bool
    synced_documents: int = 0
    synced_chunks: int = 0
    message: str


class FileAllowlistRequest(BaseModel):
    """Allowlist file/folder paths for indexing."""

    paths: list[str] = Field(min_length=1, max_length=100)


class FileAllowlistResponse(BaseModel):
    """Allowlist update response."""

    accepted: bool
    paths: list[str]


class PersonalFeedbackRequest(BaseModel):
    """Feedback request for personal runs."""

    run_id: str = Field(min_length=1, max_length=64)
    verdict: FeedbackVerdict
    comment: str | None = Field(default=None, max_length=4000)
    corrected_answer: str | None = Field(default=None, max_length=4000)
    corrected_filters: list[PersonalSource] = Field(default_factory=list)
    corrected_source_scope: str | None = Field(default=None, max_length=256)


class PersonalFeedbackResponse(BaseModel):
    """Feedback ingestion acknowledgement."""

    run_id: str
    accepted: bool
    feedback_id: int | None = None
    memory_candidate_ids: list[int] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MemoryCandidate(BaseModel):
    """Memory candidate waiting for review."""

    id: int
    run_id: str | None = None
    kind: MemoryKind
    scope: MemoryScope
    title: str
    learning: str
    confidence: int = Field(ge=0, le=100)
    evidence_citation_ids: list[str] = Field(default_factory=list)
    status: MemoryCandidateStatus
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class MemoryItem(BaseModel):
    """Active or historical memory item."""

    id: int
    kind: MemoryKind
    scope: MemoryScope
    statement: str
    activation_state: MemoryActivationState
    confidence: int = Field(ge=0, le=100)
    source: str
    supersedes_id: int | None = None
    last_verified_at: datetime | None = None
    expiry_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class MemoryCandidatesResponse(BaseModel):
    """Response payload for memory candidates list."""

    candidates: list[MemoryCandidate]


class MemoryActiveResponse(BaseModel):
    """Response payload for active memory list."""

    items: list[MemoryItem]


class MemoryActionResponse(BaseModel):
    """Memory candidate/item action response."""

    accepted: bool
    message: str
    item: MemoryItem | None = None


class MemoryEvalResponse(BaseModel):
    """Snapshot of memory efficacy metrics."""

    status: RunStatus
    message: str
    repeated_error_reduction_pct: float
    avg_retry_reduction_pct: float
    citation_compliance_pct: float
    runs_analyzed: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
