"""SQL drafting from retrieved knowledge."""

from dataclasses import dataclass

from dash.native.retrieval import RetrievedContext

FALLBACK_SQL = """\
SELECT 1 AS fallback_result
"""


@dataclass(frozen=True)
class SqlDraft:
    """Draft SQL proposal and its source metadata."""

    sql: str
    source: str
    rationale: str


class SqlDrafter:
    """Selects the best local query pattern for a question."""

    def draft(self, question: str, contexts: list[RetrievedContext]) -> SqlDraft:
        """Draft SQL using the top matching query pattern, or a safe fallback."""
        for item in contexts:
            if item.chunk.kind != "query_pattern":
                continue
            sql = item.chunk.metadata.get("sql", "").strip()
            if not sql:
                continue
            query_name = item.chunk.metadata.get("query_name", item.chunk.title)
            return SqlDraft(
                sql=sql,
                source=f"query_pattern:{query_name}",
                rationale=f"Selected highest-ranked query pattern for question: {question}",
            )
        return SqlDraft(
            sql=FALLBACK_SQL,
            source="fallback:safe_select",
            rationale="No matching query pattern found; using safe cross-database fallback query.",
        )
