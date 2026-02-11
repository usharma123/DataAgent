"""FastAPI router for native Vault contracts."""

from fastapi import APIRouter, HTTPException, status

from dash.native.contracts import (
    AskRequest,
    AskResponse,
    EvalsRunRequest,
    EvalsRunResponse,
    FeedbackRequest,
    FeedbackResponse,
    SaveQueryRequest,
    SaveQueryResponse,
)
from dash.native.guardrails import (
    SqlGuardrailError,
    load_sql_guardrail_config,
    validate_and_normalize_sql,
)
from dash.native.learning import LearningEngine
from dash.native.runtime import get_native_eval_runner, get_native_orchestrator, get_native_run_store
from dash.native.store import NativeRunStoreError

native_router = APIRouter(prefix="/native/v1", tags=["native"])


@native_router.get("/health")
def health() -> dict[str, str]:
    """Health endpoint for the native runtime surface."""
    return {"status": "ok"}


@native_router.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    """Run an ask request through the native orchestrator."""
    guardrails = load_sql_guardrail_config()
    if payload.max_sql_attempts > guardrails.max_sql_attempts:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"max_sql_attempts={payload.max_sql_attempts} exceeds allowed "
                f"value {guardrails.max_sql_attempts}"
            ),
        )

    try:
        orchestrator = get_native_orchestrator()
        return orchestrator.run_ask(payload)
    except Exception as exc:
        return AskResponse(status="failed", error=f"Native orchestrator unavailable: {exc}")


@native_router.post("/feedback", response_model=FeedbackResponse)
def feedback(payload: FeedbackRequest) -> FeedbackResponse:
    """Accept user feedback for future learning ingestion."""
    run_store = get_native_run_store()
    learning_engine = LearningEngine()
    try:
        feedback_id = run_store.create_feedback_event(
            run_id=payload.run_id,
            verdict=payload.verdict,
            comment=payload.comment,
            corrected_answer=payload.corrected_answer,
            corrected_sql=payload.corrected_sql,
        )
        learning_candidate_id: int | None = None
        learning_candidate = learning_engine.from_feedback(
            verdict=payload.verdict,
            comment=payload.comment,
            corrected_answer=payload.corrected_answer,
            corrected_sql=payload.corrected_sql,
        )
        if learning_candidate:
            learning_candidate_id = run_store.create_learning_candidate(
                run_id=payload.run_id,
                source=learning_candidate.source,
                title=learning_candidate.title,
                learning=learning_candidate.learning,
                confidence=learning_candidate.confidence,
                metadata_dict=learning_candidate.metadata,
            )
        return FeedbackResponse(
            run_id=payload.run_id,
            accepted=True,
            feedback_id=feedback_id,
            learning_candidate_id=learning_candidate_id,
        )
    except NativeRunStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@native_router.post("/save-query", response_model=SaveQueryResponse)
def save_query(payload: SaveQueryRequest) -> SaveQueryResponse:
    """Accept validated query saves and enforce SQL read-only constraints."""
    try:
        normalized_query = validate_and_normalize_sql(payload.query)
    except SqlGuardrailError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    run_store = get_native_run_store()
    try:
        query_id = run_store.save_validated_query(
            name=payload.name,
            question=payload.question,
            query=normalized_query,
            summary=payload.summary,
            tables_used=payload.tables_used,
            data_quality_notes=payload.data_quality_notes,
        )
    except NativeRunStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return SaveQueryResponse(query_name=payload.name, accepted=True, query_id=query_id)


@native_router.post("/evals/run", response_model=EvalsRunResponse)
def run_evals(payload: EvalsRunRequest) -> EvalsRunResponse:
    """Run native evaluation suite and persist summary."""
    runner = get_native_eval_runner()
    try:
        summary = runner.run(category=payload.category)
    except Exception as exc:
        return EvalsRunResponse(status="failed", message=f"Native evals failed: {exc}")
    return EvalsRunResponse(
        run_id=summary.run_id,
        status="success",
        message=f"Native eval run finished with {summary.passed}/{summary.total} passing",
        total=summary.total,
        passed=summary.passed,
        failed=summary.failed,
        duration_ms=summary.duration_ms,
    )
