"""Learning and reflection helpers for personal memory system."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryCandidateDraft:
    """Candidate memory emitted from runtime reflection."""

    kind: str
    scope: str
    title: str
    learning: str
    confidence: int
    evidence_citation_ids: list[str]
    metadata: dict[str, str]


class PersonalReflectionEngine:
    """Generate memory candidates from ask outcomes and user feedback."""

    def from_ask_outcome(
        self,
        *,
        question: str,
        outcome_class: str,
        citations: list[str],
        missing_evidence: list[str],
        memory_used_count: int,
        source_filters: list[str],
    ) -> list[MemoryCandidateDraft]:
        """Turn run outcomes into reviewable memory candidates."""
        drafts: list[MemoryCandidateDraft] = []

        if outcome_class == "success" and citations:
            drafts.append(
                MemoryCandidateDraft(
                    kind="ReasoningRule",
                    scope="user-global",
                    title="successful retrieval pattern",
                    learning=(
                        f"Question pattern succeeded: {question}\n"
                        "Preserve cited-answer workflow and prioritize retrieved evidence before synthesis."
                    ),
                    confidence=70,
                    evidence_citation_ids=citations[:3],
                    metadata={"trigger": "success", "memory_used": str(memory_used_count)},
                )
            )

        if outcome_class in {"partial", "failure", "hallucination-risk"}:
            drafts.append(
                MemoryCandidateDraft(
                    kind="GuardrailException",
                    scope="user-global",
                    title="insufficient evidence fallback",
                    learning=(
                        "When retrieved evidence is weak, do not speculate. Return uncertainty with suggested "
                        "filters/time ranges and ask for narrower scope."
                    ),
                    confidence=88,
                    evidence_citation_ids=citations[:2],
                    metadata={"trigger": outcome_class, "missing_count": str(len(missing_evidence))},
                )
            )

        if missing_evidence:
            drafts.append(
                MemoryCandidateDraft(
                    kind="UserPreference",
                    scope="user-global",
                    title="prefer guidance when evidence missing",
                    learning=(
                        "If evidence is missing, provide explicit gaps and suggest source/time filters before "
                        "attempting another answer."
                    ),
                    confidence=78,
                    evidence_citation_ids=citations[:2],
                    metadata={"trigger": "missing_evidence"},
                )
            )

        if source_filters and missing_evidence:
            for source in source_filters[:2]:
                drafts.append(
                    MemoryCandidateDraft(
                        kind="SourceQuirk",
                        scope="source-specific",
                        title=f"{source} retrieval scope hint",
                        learning=(
                            f"For {source}, missing evidence often indicates scope or time filtering issues. "
                            "Expand source-specific range before answering."
                        ),
                        confidence=68,
                        evidence_citation_ids=citations[:2],
                        metadata={"source": source, "trigger": "source_missing_evidence"},
                    )
                )

        return drafts

    def from_feedback(
        self,
        *,
        verdict: str,
        comment: str | None,
        corrected_answer: str | None,
        corrected_filters: list[str],
        corrected_source_scope: str | None,
        evidence_citation_ids: list[str],
    ) -> list[MemoryCandidateDraft]:
        """Generate memory candidates from direct feedback."""
        if verdict != "incorrect":
            return []

        detail = []
        if comment:
            detail.append(f"User comment: {comment}")
        if corrected_answer:
            detail.append(f"Corrected answer: {corrected_answer}")
        if corrected_filters:
            detail.append(f"Corrected filters: {', '.join(corrected_filters)}")
        if corrected_source_scope:
            detail.append(f"Source scope note: {corrected_source_scope}")
        if not detail:
            detail.append("User marked answer as incorrect without details.")

        drafts = [
            MemoryCandidateDraft(
                kind="ReasoningRule",
                scope="user-global",
                title="user correction received",
                learning="\n".join(detail),
                confidence=75,
                evidence_citation_ids=evidence_citation_ids,
                metadata={"trigger": "feedback"},
            )
        ]
        for source in corrected_filters[:2]:
            drafts.append(
                MemoryCandidateDraft(
                    kind="SourceQuirk",
                    scope="source-specific",
                    title=f"{source} correction pattern",
                    learning=(
                        f"User correction indicates source-specific nuance for {source}. "
                        "Prioritize this source and verify timestamps/participants before answering."
                    ),
                    confidence=72,
                    evidence_citation_ids=evidence_citation_ids,
                    metadata={"trigger": "feedback", "source": source},
                )
            )
        return drafts


def classify_outcome(*, has_error: bool, has_evidence: bool, citations_valid: bool) -> str:
    """Classify execution outcome for reflection and analytics."""
    if has_error:
        return "failure"
    if not has_evidence:
        return "partial"
    if has_evidence and not citations_valid:
        return "hallucination-risk"
    return "success"
