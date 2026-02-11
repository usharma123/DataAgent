"""Unified Vault orchestrator — auto-routes questions and feeds shared memory."""

import logging
from uuid import uuid4

from dash.contracts import VaultAskRequest, VaultAskResponse
from dash.llm import complete
from dash.native.contracts import AskRequest
from dash.native.orchestrator import NativeOrchestrator
from dash.personal.contracts import PersonalAskRequest
from dash.personal.learning import PersonalReflectionEngine
from dash.personal.memory import MemoryManager
from dash.personal.orchestrator import PersonalOrchestrator
from dash.personal.store import PersonalStore, PersonalStoreError

logger = logging.getLogger(__name__)

INTENT_SYSTEM = (
    "You are a routing classifier. Given a user question, respond with exactly one word:\n"
    "- 'sql' if the question is about structured data, databases, tables, statistics, or counts\n"
    "- 'personal' if the question is about personal data like emails, messages, files, or contacts\n"
    "- 'both' if the question spans both structured data and personal data\n"
    "Respond with only the word: sql, personal, or both."
)

MERGE_SYSTEM = (
    "You are a helpful assistant. Combine the following two answers into a single coherent response. "
    "Preserve citations from both. Be concise (3-5 sentences)."
)


class VaultOrchestrator:
    """Top-level orchestrator that auto-routes and feeds shared memory."""

    def __init__(
        self,
        *,
        native: NativeOrchestrator,
        personal: PersonalOrchestrator,
        store: PersonalStore,
        memory_manager: MemoryManager,
        reflection_engine: PersonalReflectionEngine,
    ):
        self._native = native
        self._personal = personal
        self._store = store
        self._memory_manager = memory_manager
        self._reflection_engine = reflection_engine

    def run_ask(
        self,
        payload: VaultAskRequest,
        force_mode: str | None = None,
    ) -> VaultAskResponse:
        """Classify, select memory, route, reflect, and return unified response."""
        run_id = str(uuid4())

        # 1. Classify intent
        mode = force_mode or self._classify_intent(payload.question)

        # 2. Select memories from shared store
        memory_used: list[str] = []
        memory_hints: list[str] = []
        try:
            selected = self._memory_manager.select_for_question(
                question=payload.question,
                session_id=payload.session_id,
                source_filters=payload.source_filters,
            )
            memory_used = [f"{m['id']}:{m['kind']}" for m in selected.used]
            memory_hints = [
                str(m["statement"]).split("\n")[0][:200] for m in selected.used
            ]
        except PersonalStoreError:
            logger.warning("Memory selection failed", exc_info=True)

        # 3. Route
        if mode == "sql":
            return self._run_sql(payload, run_id=run_id, memory_used=memory_used, memory_hints=memory_hints)
        elif mode == "personal":
            return self._run_personal(payload, run_id=run_id, memory_used=memory_used)
        else:
            return self._run_both(payload, run_id=run_id, memory_used=memory_used, memory_hints=memory_hints)

    def _classify_intent(self, question: str) -> str:
        """Use LLM to classify question intent."""
        try:
            response = complete(
                system=INTENT_SYSTEM,
                user=question,
                temperature=0.0,
                max_tokens=10,
            )
            mode = response.strip().lower()
            if mode in ("sql", "personal", "both"):
                return mode
        except Exception:
            logger.warning("Intent classification failed, defaulting to personal", exc_info=True)
        return "personal"

    def _run_sql(
        self,
        payload: VaultAskRequest,
        *,
        run_id: str,
        memory_used: list[str],
        memory_hints: list[str],
    ) -> VaultAskResponse:
        """Execute SQL path and reflect."""
        native_req = AskRequest(
            question=payload.question,
            user_id=payload.user_id,
            session_id=payload.session_id,
            include_debug=payload.include_debug,
            max_sql_attempts=payload.max_sql_attempts,
        )
        result = self._native.run_ask(native_req, memory_hints=memory_hints)

        # 4. Reflect — write SQL outcomes to shared memory
        self._reflect_sql(
            run_id=result.run_id,
            question=payload.question,
            sql=result.sql,
            rows=result.rows,
            error=result.error,
        )

        return VaultAskResponse(
            run_id=result.run_id,
            status=result.status,
            mode="sql",
            answer=result.answer,
            sql=result.sql,
            rows=result.rows,
            memory_used=memory_used,
            error=result.error,
            debug={"sql_attempts": [a.model_dump() for a in result.sql_attempts]} if result.sql_attempts else None,
        )

    def _run_personal(
        self,
        payload: VaultAskRequest,
        *,
        run_id: str,
        memory_used: list[str],
    ) -> VaultAskResponse:
        """Execute personal path (already has memory internally)."""
        personal_req = PersonalAskRequest(
            question=payload.question,
            user_id=payload.user_id,
            session_id=payload.session_id,
            source_filters=payload.source_filters,
            time_from=payload.time_from,
            time_to=payload.time_to,
            top_k=payload.top_k,
            include_debug=payload.include_debug,
        )
        result = self._personal.run_ask(personal_req)

        return VaultAskResponse(
            run_id=result.run_id,
            status=result.status,
            mode="personal",
            answer=result.answer,
            citations=result.citations,
            missing_evidence=result.missing_evidence,
            memory_used=memory_used,
            error=result.error,
            debug=result.debug.model_dump() if result.debug else None,
        )

    def _run_both(
        self,
        payload: VaultAskRequest,
        *,
        run_id: str,
        memory_used: list[str],
        memory_hints: list[str],
    ) -> VaultAskResponse:
        """Run both runtimes and merge answers."""
        sql_resp = self._run_sql(payload, run_id=run_id, memory_used=memory_used, memory_hints=memory_hints)
        personal_resp = self._run_personal(payload, run_id=run_id, memory_used=memory_used)

        # Merge answers
        parts = []
        if sql_resp.answer:
            parts.append(f"Data answer: {sql_resp.answer}")
        if personal_resp.answer:
            parts.append(f"Personal answer: {personal_resp.answer}")

        if len(parts) == 2:
            try:
                merged = complete(
                    system=MERGE_SYSTEM,
                    user="\n\n".join(parts),
                    temperature=0.2,
                    max_tokens=512,
                )
            except Exception:
                merged = "\n\n".join(parts)
        else:
            merged = parts[0] if parts else None

        # Pick the best status
        status = "success" if sql_resp.status == "success" or personal_resp.status == "success" else "failed"

        return VaultAskResponse(
            run_id=run_id,
            status=status,
            mode="both",
            answer=merged,
            sql=sql_resp.sql,
            rows=sql_resp.rows,
            citations=personal_resp.citations,
            missing_evidence=personal_resp.missing_evidence,
            memory_used=memory_used,
            error=sql_resp.error or personal_resp.error,
        )

    def _reflect_sql(
        self,
        *,
        run_id: str,
        question: str,
        sql: str | None,
        rows: list[dict] | None,
        error: str | None,
    ) -> None:
        """Write SQL outcome reflections into the shared memory store."""
        try:
            drafts = self._reflection_engine.from_sql_outcome(
                run_id=run_id,
                question=question,
                sql=sql,
                rows=rows,
                error=error,
            )
            for draft in drafts:
                self._store.create_memory_candidate(
                    run_id=run_id,
                    kind=draft.kind,
                    scope=draft.scope,
                    title=draft.title,
                    learning=draft.learning,
                    confidence=draft.confidence,
                    evidence_citation_ids=draft.evidence_citation_ids,
                    status="proposed",
                    metadata_dict=draft.metadata,
                )
        except PersonalStoreError:
            logger.warning("Failed to write SQL reflection candidates", exc_info=True)
