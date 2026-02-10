"""Learning candidate generation for native Dash."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LearningCandidateDraft:
    """A candidate learning extracted from an error or correction."""

    source: str
    title: str
    learning: str
    confidence: int
    metadata: dict[str, str]


class LearningEngine:
    """Simple deterministic learning extraction from failures and feedback."""

    def from_sql_error(
        self,
        *,
        question: str,
        sql: str,
        error: str,
    ) -> LearningCandidateDraft:
        """Convert SQL execution failures into learning candidates."""
        category, confidence = _classify_sql_error(error)
        title = f"{category}: query failure pattern"
        learning = (
            f"Question: {question}\n"
            f"Error: {error}\n"
            f"Suggested fix: {_suggest_fix(category)}"
        )
        return LearningCandidateDraft(
            source="sql_error",
            title=title,
            learning=learning,
            confidence=confidence,
            metadata={"category": category, "sql": sql[:2000]},
        )

    def from_feedback(
        self,
        *,
        verdict: str,
        comment: str | None,
        corrected_answer: str | None,
        corrected_sql: str | None,
    ) -> LearningCandidateDraft | None:
        """Convert negative feedback into learning candidates."""
        if verdict != "incorrect":
            return None
        insight_parts = []
        if comment:
            insight_parts.append(f"User comment: {comment}")
        if corrected_answer:
            insight_parts.append(f"Correct answer: {corrected_answer}")
        if corrected_sql:
            insight_parts.append(f"Corrected SQL: {corrected_sql}")
        if not insight_parts:
            insight_parts.append("User marked response as incorrect without details.")
        return LearningCandidateDraft(
            source="user_feedback",
            title="user_feedback: correction received",
            learning="\n".join(insight_parts),
            confidence=75,
            metadata={},
        )


def _classify_sql_error(error: str) -> tuple[str, int]:
    lower = error.lower()
    if "does not exist" in lower and "column" in lower:
        return "schema_mismatch", 80
    if "operator does not exist" in lower or "invalid input syntax" in lower:
        return "type_mismatch", 85
    if "syntax error" in lower:
        return "sql_syntax", 65
    if "statement timeout" in lower or "canceling statement due to statement timeout" in lower:
        return "query_timeout", 70
    if "permission denied" in lower:
        return "permissions", 90
    return "execution_error", 60


def _suggest_fix(category: str) -> str:
    if category == "schema_mismatch":
        return "Re-run schema introspection and verify column/table names."
    if category == "type_mismatch":
        return "Check data types and add explicit casts or quoted literals."
    if category == "sql_syntax":
        return "Validate SQL syntax and simplify the query."
    if category == "query_timeout":
        return "Reduce scanned rows, add filters, and verify indexes."
    if category == "permissions":
        return "Use allowed schemas/tables with the read-only role."
    return "Inspect query and error details, then retry with tighter constraints."
