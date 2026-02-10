"""FastAPI router for personal data agent endpoints."""

from fastapi import APIRouter, HTTPException, Query, status

from dash.personal.contracts import (
    ConnectSourceRequest,
    FileAllowlistRequest,
    FileAllowlistResponse,
    MemoryActionResponse,
    MemoryActiveResponse,
    MemoryCandidatesResponse,
    MemoryEvalResponse,
    PersonalAskRequest,
    PersonalAskResponse,
    PersonalFeedbackRequest,
    PersonalFeedbackResponse,
    SourceStatus,
    SourceStatusResponse,
    SyncSourceRequest,
    SyncSourceResponse,
)
from dash.personal.learning import PersonalReflectionEngine
from dash.personal.runtime import (
    get_memory_eval_runner,
    get_memory_manager,
    get_personal_orchestrator,
    get_personal_store,
)
from dash.personal.store import PersonalStoreError
from dash.personal.sync import PersonalSyncService

personal_router = APIRouter(prefix="/native/v1/personal", tags=["personal"])
_VALID_SOURCES = {"gmail", "slack", "imessage", "files"}


@personal_router.post("/ask", response_model=PersonalAskResponse)
def ask(payload: PersonalAskRequest) -> PersonalAskResponse:
    """Run personal ask with memory and citation constraints."""
    orchestrator = get_personal_orchestrator()
    return orchestrator.run_ask(payload)


@personal_router.get("/sources/status", response_model=SourceStatusResponse)
def source_status() -> SourceStatusResponse:
    """List source connection/sync status."""
    store = get_personal_store()
    try:
        rows = store.list_sources()
    except PersonalStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return SourceStatusResponse(
        sources=[
            SourceStatus(
                source=row["source"],
                connected=bool(row["connected"]),
                last_sync_at=row.get("last_sync_at"),
                cursor=row.get("cursor"),
            )
            for row in rows
            if row.get("source") in _VALID_SOURCES
        ]
    )


@personal_router.post("/sources/{source}/connect", response_model=SyncSourceResponse)
def connect_source(source: str, payload: ConnectSourceRequest) -> SyncSourceResponse:
    """Connect one data source for personal indexing."""
    if source not in _VALID_SOURCES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown source: {source}")

    store = get_personal_store()
    sync_service = PersonalSyncService(store)
    try:
        sync_service.connect_source(source=source, cursor=payload.cursor)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return SyncSourceResponse(
        source=source,
        accepted=True,
        synced_documents=0,
        synced_chunks=0,
        message=f"{source} connected",
    )


@personal_router.post("/sources/{source}/sync", response_model=SyncSourceResponse)
def sync_source(source: str, payload: SyncSourceRequest) -> SyncSourceResponse:
    """Trigger sync for one source."""
    if source not in _VALID_SOURCES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown source: {source}")

    store = get_personal_store()
    sync_service = PersonalSyncService(store)
    try:
        docs, chunks, message = sync_service.sync_source(source=source, full=payload.full)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return SyncSourceResponse(
        source=source,
        accepted=True,
        synced_documents=docs,
        synced_chunks=chunks,
        message=message,
    )


@personal_router.post("/files/allowlist", response_model=FileAllowlistResponse)
def set_file_allowlist(payload: FileAllowlistRequest) -> FileAllowlistResponse:
    """Replace file source allowlist paths."""
    store = get_personal_store()
    try:
        store.replace_file_allowlist(payload.paths)
        paths = store.list_file_allowlist()
    except PersonalStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return FileAllowlistResponse(accepted=True, paths=paths)


@personal_router.get("/citations/{citation_id}")
def citation(citation_id: str) -> dict:
    """Get one citation payload."""
    store = get_personal_store()
    try:
        row = store.get_citation(citation_id)
    except PersonalStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Citation not found")
    return row


@personal_router.get("/memory/candidates", response_model=MemoryCandidatesResponse)
def memory_candidates(status_filter: str = Query(default="proposed", alias="status")) -> MemoryCandidatesResponse:
    """List memory candidates."""
    store = get_personal_store()
    normalized = status_filter.strip().lower()
    if normalized == "all":
        normalized = ""
    try:
        rows = store.list_memory_candidates(status=normalized or None)
    except PersonalStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return MemoryCandidatesResponse(candidates=rows)


@personal_router.post("/memory/candidates/{candidate_id}/approve", response_model=MemoryActionResponse)
def approve_memory(candidate_id: int) -> MemoryActionResponse:
    """Approve and activate a memory candidate."""
    manager = get_memory_manager()
    try:
        item, demoted = manager.approve_candidate(candidate_id)
    except PersonalStoreError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    message = "Memory candidate approved and activated"
    if demoted:
        message += f"; auto-demoted conflicts: {demoted}"
    return MemoryActionResponse(accepted=True, message=message, item=item)


@personal_router.post("/memory/candidates/{candidate_id}/reject", response_model=MemoryActionResponse)
def reject_memory(candidate_id: int) -> MemoryActionResponse:
    """Reject memory candidate."""
    manager = get_memory_manager()
    try:
        manager.reject_candidate(candidate_id)
    except PersonalStoreError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return MemoryActionResponse(accepted=True, message="Memory candidate rejected", item=None)


@personal_router.get("/memory/active", response_model=MemoryActiveResponse)
def memory_active() -> MemoryActiveResponse:
    """List active memory items."""
    store = get_personal_store()
    try:
        items = store.list_memory_items(active_only=True)
    except PersonalStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return MemoryActiveResponse(items=items)


@personal_router.post("/memory/{item_id}/deprecate", response_model=MemoryActionResponse)
def deprecate_memory(item_id: int) -> MemoryActionResponse:
    """Deprecate active memory item."""
    manager = get_memory_manager()
    store = get_personal_store()
    try:
        manager.deprecate_item(item_id)
        updated = store.get_memory_item(item_id)
    except PersonalStoreError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return MemoryActionResponse(accepted=True, message="Memory deprecated", item=updated)


@personal_router.post("/feedback", response_model=PersonalFeedbackResponse)
def feedback(payload: PersonalFeedbackRequest) -> PersonalFeedbackResponse:
    """Capture personal feedback and emit memory candidates."""
    store = get_personal_store()
    try:
        feedback_id = store.create_feedback_event(
            run_id=payload.run_id,
            verdict=payload.verdict,
            comment=payload.comment,
            corrected_answer=payload.corrected_answer,
            corrected_filters=payload.corrected_filters,
            corrected_source_scope=payload.corrected_source_scope,
        )
        evidence = store.list_citations_for_run(payload.run_id)
        reflection = PersonalReflectionEngine()
        drafts = reflection.from_feedback(
            verdict=payload.verdict,
            comment=payload.comment,
            corrected_answer=payload.corrected_answer,
            corrected_filters=payload.corrected_filters,
            corrected_source_scope=payload.corrected_source_scope,
            evidence_citation_ids=evidence[:5],
        )
        candidate_ids: list[int] = []
        for draft in drafts:
            if not draft.evidence_citation_ids:
                continue
            candidate_ids.append(
                store.create_memory_candidate(
                    run_id=payload.run_id,
                    kind=draft.kind,
                    scope=draft.scope,
                    title=draft.title,
                    learning=draft.learning,
                    confidence=draft.confidence,
                    evidence_citation_ids=draft.evidence_citation_ids,
                    status="proposed",
                    metadata_dict=draft.metadata,
                )
            )
    except PersonalStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return PersonalFeedbackResponse(
        run_id=payload.run_id,
        accepted=True,
        feedback_id=feedback_id,
        memory_candidate_ids=candidate_ids,
    )


@personal_router.get("/evals/memory", response_model=MemoryEvalResponse)
def eval_memory() -> MemoryEvalResponse:
    """Run memory efficacy snapshot evaluation."""
    runner = get_memory_eval_runner()
    try:
        summary = runner.run()
    except PersonalStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return MemoryEvalResponse(
        status="success",
        message="memory eval completed",
        repeated_error_reduction_pct=summary.repeated_error_reduction_pct,
        avg_retry_reduction_pct=summary.avg_retry_reduction_pct,
        citation_compliance_pct=summary.citation_compliance_pct,
        runs_analyzed=summary.runs_analyzed,
    )
