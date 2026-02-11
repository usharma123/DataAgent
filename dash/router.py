"""Unified Vault API router — single /v1/ask endpoint with auto-routing."""

from fastapi import APIRouter, HTTPException, Query, status

from dash.contracts import VaultAskRequest, VaultAskResponse, VaultFeedbackRequest, VaultFeedbackResponse
from dash.personal.contracts import (
    MemoryActionResponse,
    MemoryActiveResponse,
    MemoryCandidatesResponse,
)
from dash.personal.learning import PersonalReflectionEngine
from dash.personal.runtime import get_memory_manager, get_personal_store
from dash.personal.store import PersonalStoreError
from dash.runtime import get_vault_orchestrator

vault_router = APIRouter(prefix="/v1", tags=["vault"])


@vault_router.post("/ask", response_model=VaultAskResponse)
def ask(payload: VaultAskRequest) -> VaultAskResponse:
    """Unified ask endpoint — auto-routes to SQL, personal, or both."""
    orchestrator = get_vault_orchestrator()
    return orchestrator.run_ask(payload)


@vault_router.post("/feedback", response_model=VaultFeedbackResponse)
def feedback(payload: VaultFeedbackRequest) -> VaultFeedbackResponse:
    """Unified feedback endpoint — routes to correct store based on mode."""
    store = get_personal_store()

    if payload.mode == "sql":
        # SQL feedback: create memory candidates via reflection engine
        reflection = PersonalReflectionEngine()
        drafts = reflection.from_sql_outcome(
            run_id=payload.run_id,
            question="(from feedback)",
            sql=payload.corrected_sql,
            rows=None,
            error=None,
            corrected_sql=payload.corrected_sql,
        )
        candidate_ids: list[int] = []
        try:
            for draft in drafts:
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

        return VaultFeedbackResponse(
            run_id=payload.run_id,
            accepted=True,
            memory_candidate_ids=candidate_ids,
        )
    else:
        # Personal feedback: existing flow
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
            candidate_ids = []
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

        return VaultFeedbackResponse(
            run_id=payload.run_id,
            accepted=True,
            feedback_id=feedback_id,
            memory_candidate_ids=candidate_ids,
        )


# --- Re-export memory endpoints under /v1/memory ---


@vault_router.get("/memory/candidates", response_model=MemoryCandidatesResponse)
def memory_candidates(status_filter: str = Query(default="proposed", alias="status")) -> MemoryCandidatesResponse:
    """List memory candidates (shared across SQL and personal)."""
    store = get_personal_store()
    normalized = status_filter.strip().lower()
    if normalized == "all":
        normalized = ""
    try:
        rows = store.list_memory_candidates(status=normalized or None)
    except PersonalStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return MemoryCandidatesResponse(candidates=rows)


@vault_router.post("/memory/candidates/{candidate_id}/approve", response_model=MemoryActionResponse)
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


@vault_router.post("/memory/candidates/{candidate_id}/reject", response_model=MemoryActionResponse)
def reject_memory(candidate_id: int) -> MemoryActionResponse:
    """Reject memory candidate."""
    manager = get_memory_manager()
    try:
        manager.reject_candidate(candidate_id)
    except PersonalStoreError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return MemoryActionResponse(accepted=True, message="Memory candidate rejected", item=None)


@vault_router.get("/memory/active", response_model=MemoryActiveResponse)
def memory_active() -> MemoryActiveResponse:
    """List active memory items."""
    store = get_personal_store()
    try:
        items = store.list_memory_items(active_only=True)
    except PersonalStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return MemoryActiveResponse(items=items)


@vault_router.post("/memory/{item_id}/deprecate", response_model=MemoryActionResponse)
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
