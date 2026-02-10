"""Native orchestration skeleton for ask runs."""

from uuid import uuid4

from dash.native.contracts import AskRequest, AskResponse, SqlAttempt
from dash.native.executor import SqlExecutionError, SqlExecutor
from dash.native.guardrails import SqlGuardrailError, validate_and_normalize_sql
from dash.native.insights import summarize_rows
from dash.native.learning import LearningEngine
from dash.native.retrieval import LocalKnowledgeRetriever
from dash.native.sql_drafter import FALLBACK_SQL, SqlDrafter
from dash.native.store import NativeRunStore, NativeRunStoreError


class NativeOrchestrator:
    """Minimal native orchestrator with durable run logging."""

    def __init__(
        self,
        run_store: NativeRunStore,
        sql_executor: SqlExecutor,
        learning_engine: LearningEngine,
        retriever: LocalKnowledgeRetriever,
        sql_drafter: SqlDrafter,
    ):
        self._run_store = run_store
        self._sql_executor = sql_executor
        self._learning_engine = learning_engine
        self._retriever = retriever
        self._sql_drafter = sql_drafter

    def run_ask(self, payload: AskRequest) -> AskResponse:
        """Persist an ask run, draft SQL, execute, and return tracked metadata."""
        run_id = str(uuid4())
        try:
            self._run_store.create_query_run(
                run_id=run_id,
                status="accepted",
                question=payload.question,
                user_id=payload.user_id,
                session_id=payload.session_id,
                max_sql_attempts=payload.max_sql_attempts,
            )
        except NativeRunStoreError as exc:
            return AskResponse(
                run_id=run_id,
                status="failed",
                error=f"Could not persist query run: {exc}",
            )

        normalized_sql = ""
        attempts: list[dict[str, str | int | None]] = []
        rows: list[dict[str, object]] = []
        try:
            contexts = self._retriever.retrieve(payload.question)
            draft = self._sql_drafter.draft(payload.question, contexts)
            primary_sql = validate_and_normalize_sql(draft.sql)
            sql_candidates = [primary_sql]
            if payload.max_sql_attempts > 1:
                fallback_sql = validate_and_normalize_sql(FALLBACK_SQL)
                if fallback_sql.lower().strip() != primary_sql.lower().strip():
                    sql_candidates.append(fallback_sql)

            final_sql = primary_sql
            last_error: str | None = None
            for attempt_number, candidate_sql in enumerate(
                sql_candidates[: payload.max_sql_attempts],
                start=1,
            ):
                final_sql = candidate_sql
                try:
                    exec_result = self._sql_executor.execute(candidate_sql)
                    rows = exec_result.rows
                    self._run_store.log_sql_attempt(
                        run_id=run_id,
                        attempt_number=attempt_number,
                        sql=candidate_sql,
                        error=None,
                    )
                    break
                except SqlExecutionError as exc:
                    last_error = str(exc)
                    self._run_store.log_sql_attempt(
                        run_id=run_id,
                        attempt_number=attempt_number,
                        sql=candidate_sql,
                        error=last_error,
                    )
                    candidate = self._learning_engine.from_sql_error(
                        question=payload.question,
                        sql=candidate_sql,
                        error=last_error,
                    )
                    self._run_store.create_learning_candidate(
                        run_id=run_id,
                        source=candidate.source,
                        title=candidate.title,
                        learning=candidate.learning,
                        confidence=candidate.confidence,
                        metadata_dict=candidate.metadata,
                    )
                    if attempt_number >= min(len(sql_candidates), payload.max_sql_attempts):
                        raise SqlExecutionError(last_error) from exc

            normalized_sql = final_sql
            attempts = self._run_store.list_sql_attempts(run_id=run_id)
            answer = summarize_rows(payload.question, rows)
            self._run_store.update_query_run(run_id=run_id, status="success", answer=answer)
        except NativeRunStoreError as exc:
            try:
                self._run_store.update_query_run(run_id=run_id, status="failed", error=str(exc))
            except NativeRunStoreError:
                pass
            return AskResponse(
                run_id=run_id,
                status="failed",
                error=f"Run failed while logging state: {exc}",
            )
        except SqlExecutionError as exc:
            try:
                attempts = self._run_store.list_sql_attempts(run_id=run_id)
            except NativeRunStoreError:
                attempts = []
            try:
                self._run_store.update_query_run(run_id=run_id, status="failed", error=str(exc))
            except NativeRunStoreError:
                pass
            return AskResponse(
                run_id=run_id,
                status="failed",
                sql=(normalized_sql or draft.sql) if payload.include_debug else None,
                sql_attempts=(
                    [
                        SqlAttempt(
                            attempt_number=a["attempt_number"],
                            sql=a["sql"],
                            error=a["error"],
                        )
                        for a in attempts
                    ]
                    if payload.include_debug
                    else None
                ),
                error=f"SQL execution failed: {exc}",
            )
        except SqlGuardrailError as exc:
            try:
                self._run_store.log_sql_attempt(run_id=run_id, attempt_number=1, sql=draft.sql, error=str(exc))
            except NativeRunStoreError:
                pass
            try:
                attempts = self._run_store.list_sql_attempts(run_id=run_id)
            except NativeRunStoreError:
                attempts = []
            try:
                self._run_store.update_query_run(run_id=run_id, status="failed", error=str(exc))
            except NativeRunStoreError:
                pass
            return AskResponse(
                run_id=run_id,
                status="failed",
                sql=(normalized_sql or draft.sql) if payload.include_debug else None,
                sql_attempts=(
                    [
                        SqlAttempt(
                            attempt_number=a["attempt_number"],
                            sql=a["sql"],
                            error=a["error"],
                        )
                        for a in attempts
                    ]
                    if payload.include_debug
                    else None
                ),
                error=f"Drafted SQL did not pass guardrails: {exc}",
            )
        except Exception as exc:
            try:
                self._run_store.update_query_run(run_id=run_id, status="failed", error=str(exc))
            except NativeRunStoreError:
                pass
            return AskResponse(
                run_id=run_id,
                status="failed",
                error=f"Run failed during retrieval/drafting: {exc}",
            )

        return AskResponse(
            run_id=run_id,
            status="success",
            answer=answer,
            sql=normalized_sql,
            rows=rows,
            sql_attempts=(
                [
                    SqlAttempt(
                        attempt_number=a["attempt_number"],
                        sql=a["sql"],
                        error=a["error"],
                    )
                    for a in attempts
                ]
                if payload.include_debug
                else None
            ),
        )
