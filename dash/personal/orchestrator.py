"""Orchestration for personal ask runs with memory and citation guarantees."""

from uuid import uuid4

from dash.personal.contracts import AskDebug, Citation, PersonalAskRequest, PersonalAskResponse
from dash.personal.learning import PersonalReflectionEngine, classify_outcome
from dash.personal.memory import MemoryManager
from dash.personal.retrieval import PersonalRetriever
from dash.personal.store import PersonalStore, PersonalStoreError


class PersonalOrchestrator:
    """Runs personal ask queries over indexed local data and active memory."""

    def __init__(
        self,
        *,
        store: PersonalStore,
        retriever: PersonalRetriever,
        memory_manager: MemoryManager,
        reflection_engine: PersonalReflectionEngine,
    ):
        self._store = store
        self._retriever = retriever
        self._memory_manager = memory_manager
        self._reflection_engine = reflection_engine

    def run_ask(self, payload: PersonalAskRequest) -> PersonalAskResponse:
        """Execute ask flow with evidence-only answering and memory traces."""
        run_id = str(uuid4())
        try:
            self._store.create_query_run(
                run_id=run_id,
                question=payload.question,
                user_id=payload.user_id,
                session_id=payload.session_id,
            )
        except PersonalStoreError as exc:
            return PersonalAskResponse(run_id=run_id, status="failed", error=f"Could not persist run: {exc}")

        missing_evidence: list[str] = []
        debug = AskDebug(memory_used=[], memory_skipped=[])
        answer: str | None = None
        citations: list[Citation] = []

        try:
            memory_used = []
            memory_skipped = []
            try:
                selected = self._memory_manager.select_for_question(
                    question=payload.question,
                    session_id=payload.session_id,
                    source_filters=payload.source_filters,
                )
                memory_used = selected.used
                memory_skipped = selected.skipped
            except PersonalStoreError:
                memory_skipped = []

            debug.memory_used = [
                f"{m['id']}:{m['kind']}" for m in memory_used if "id" in m and "kind" in m
            ]
            debug.memory_skipped = [
                f"{m['id']}:{m['kind']}" for m in memory_skipped if "id" in m and "kind" in m
            ]

            retrieved = self._retriever.retrieve(
                question=payload.question,
                source_filters=payload.source_filters,
                time_from=payload.time_from,
                time_to=payload.time_to,
                top_k=payload.top_k,
            )

            if not retrieved:
                missing_evidence = self._missing_evidence_hints(payload)
                answer = (
                    "Insufficient evidence found in indexed personal sources. "
                    "Try narrowing source filters or a shorter date range."
                )
                citations = []
            else:
                citation_rows = self._store.save_citations(
                    run_id=run_id,
                    items=[
                        {
                            "chunk_id": item.chunk_id,
                            "source": item.source,
                            "text": item.text,
                            "title": item.title,
                            "author": item.author,
                            "timestamp_utc": item.timestamp_utc,
                            "deep_link": item.deep_link,
                            "score": item.score,
                        }
                        for item in retrieved[: min(8, len(retrieved))]
                    ],
                )

                citation_ids = {row["citation_id"] for row in citation_rows}
                citations = [
                    Citation(
                        citation_id=row["citation_id"],
                        source=row["source"],
                        title=row.get("title"),
                        snippet=row["snippet"],
                        author=row.get("author"),
                        timestamp=row.get("timestamp"),
                        deep_link=row.get("deep_link"),
                        confidence=row.get("confidence", 0.0),
                    )
                    for row in citation_rows
                ]

                citations_valid = len(citations) > 0 and len(citation_ids) == len(citations)
                if not citations_valid:
                    missing_evidence = self._missing_evidence_hints(payload)
                    answer = (
                        "Insufficient validated evidence to answer safely. "
                        "Please retry with narrower filters."
                    )
                else:
                    answer = self._compose_answer(
                        question=payload.question,
                        citations=citations,
                        memory_used=memory_used,
                    )

            for item in memory_used:
                self._store.record_memory_usage(
                    run_id=run_id,
                    memory_item_id=int(item["id"]),
                    influence_score=0.75,
                    applied=True,
                    reason="retrieved for question",
                )
            for item in memory_skipped:
                self._store.record_memory_usage(
                    run_id=run_id,
                    memory_item_id=int(item["id"]),
                    influence_score=0.0,
                    applied=False,
                    reason="not relevant to question",
                )

            outcome = classify_outcome(
                has_error=False,
                has_evidence=len(citations) > 0,
                citations_valid=len(citations) > 0,
            )
            self._store.finalize_query_run(
                run_id=run_id,
                status="success",
                answer=answer,
                error=None,
                outcome_class=outcome,
                retries=1,
                missing_evidence=missing_evidence,
            )

            self._write_reflection_candidates(
                run_id=run_id,
                question=payload.question,
                outcome_class=outcome,
                citations=[c.citation_id for c in citations],
                missing_evidence=missing_evidence,
                memory_used_count=len(memory_used),
                source_filters=payload.source_filters,
            )

            return PersonalAskResponse(
                run_id=run_id,
                status="success",
                answer=answer,
                citations=citations,
                missing_evidence=missing_evidence,
                debug=debug if payload.include_debug else None,
            )
        except Exception as exc:
            try:
                self._store.finalize_query_run(
                    run_id=run_id,
                    status="failed",
                    answer=None,
                    error=str(exc),
                    outcome_class="failure",
                    retries=1,
                    missing_evidence=[],
                )
            except PersonalStoreError:
                pass
            return PersonalAskResponse(
                run_id=run_id,
                status="failed",
                error=f"Personal ask failed: {exc}",
                debug=debug if payload.include_debug else None,
            )

    def _compose_answer(self, *, question: str, citations: list[Citation], memory_used: list[dict]) -> str:
        """Build an answer strictly from cited evidence, using LLM when available."""
        top = citations[: min(5, len(citations))]
        evidence_lines = [f"[{idx}] ({item.source}) {item.snippet}" for idx, item in enumerate(top, start=1)]

        memory_hint = ""
        if memory_used:
            memory_hint = "\nMemory guidance: " + "; ".join(
                str(item["statement"]).split("\n")[0][:120] for item in memory_used[:2]
            )

        evidence_block = "\n".join(evidence_lines)

        try:
            from dash.llm import complete

            system = (
                "You answer questions using ONLY the cited evidence provided. "
                "Reference citations as [1], [2], etc. Be concise (2-4 sentences). "
                "If the evidence is insufficient, say so clearly. Never fabricate information."
            )
            user = (
                f"Question: {question}\n\n"
                f"Evidence:\n{evidence_block}"
                f"{memory_hint}"
            )
            return complete(system=system, user=user, temperature=0.2, max_tokens=512)
        except Exception:
            return (
                f"Answer for: {question}\n"
                "Based only on the cited evidence:\n"
                + evidence_block
                + memory_hint
            )

    def _missing_evidence_hints(self, payload: PersonalAskRequest) -> list[str]:
        hints = [
            "Try source filters: gmail, slack, imessage, files",
            "Try a tighter time range (last 7d or 30d)",
        ]
        if payload.source_filters:
            hints.append("Current source filter may be too narrow")
        if payload.time_from is not None or payload.time_to is not None:
            hints.append("Current date range may exclude relevant evidence")
        return hints

    def _write_reflection_candidates(
        self,
        *,
        run_id: str,
        question: str,
        outcome_class: str,
        citations: list[str],
        missing_evidence: list[str],
        memory_used_count: int,
        source_filters: list[str],
    ) -> None:
        drafts = self._reflection_engine.from_ask_outcome(
            question=question,
            outcome_class=outcome_class,
            citations=citations,
            missing_evidence=missing_evidence,
            memory_used_count=memory_used_count,
            source_filters=source_filters,
        )
        for draft in drafts:
            if not draft.evidence_citation_ids:
                continue
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
