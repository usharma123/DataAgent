"""SQL drafting from retrieved knowledge — LLM-powered with pattern fallback."""

from dataclasses import dataclass

from dash.context.business_rules import BUSINESS_CONTEXT
from dash.context.semantic_model import SEMANTIC_MODEL_STR
from dash.llm import complete
from dash.native.retrieval import RetrievedContext

FALLBACK_SQL = """\
SELECT 1 AS fallback_result
"""

SQL_SYSTEM_PROMPT = f"""\
You are a SQL generation engine. Given a natural language question about an F1 database,
generate a single PostgreSQL SELECT query.

Rules:
- LIMIT 50 by default
- Never SELECT * — specify columns
- ORDER BY for top-N queries
- No DROP, DELETE, UPDATE, INSERT
- Return ONLY the SQL, no explanation

## SCHEMA
{SEMANTIC_MODEL_STR}

## BUSINESS CONTEXT
{BUSINESS_CONTEXT}
"""


@dataclass(frozen=True)
class SqlDraft:
    """Draft SQL proposal and its source metadata."""

    sql: str
    source: str
    rationale: str


class SqlDrafter:
    """Drafts SQL using LLM with pattern context, falls back to pattern matching."""

    def draft(self, question: str, contexts: list[RetrievedContext]) -> SqlDraft:
        """Draft SQL using LLM informed by retrieved patterns."""
        # Gather any matching patterns for context
        pattern_context = ""
        for item in contexts:
            if item.chunk.kind != "query_pattern":
                continue
            sql = item.chunk.metadata.get("sql", "").strip()
            if sql:
                name = item.chunk.metadata.get("query_name", item.chunk.title)
                pattern_context += f"\n-- Pattern: {name}\n{sql}\n"

        user_prompt = f"Question: {question}"
        if pattern_context:
            user_prompt += f"\n\nRelevant query patterns for reference:{pattern_context}"

        try:
            response = complete(
                system=SQL_SYSTEM_PROMPT,
                user=user_prompt,
                temperature=0.1,
                max_tokens=1024,
            )
            sql = _extract_sql(response)
            if sql:
                return SqlDraft(
                    sql=sql,
                    source="llm:sql_drafter",
                    rationale=f"LLM-generated SQL for: {question}",
                )
        except Exception:
            pass

        # Fallback to pattern matching
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


def _extract_sql(response: str) -> str:
    """Extract SQL from LLM response, handling markdown fences."""
    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text
