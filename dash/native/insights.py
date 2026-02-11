"""Human-readable response synthesis for query results — LLM-powered."""

import json
from typing import Any

from dash.llm import complete

INSIGHT_SYSTEM = """\
You are a data analyst providing insights, not just data. Given a question and query results:
- Provide a concise, insightful answer (2-4 sentences)
- Highlight key comparisons, trends, or standout facts
- Use specific numbers from the data
- Don't just list the data — interpret it
"""


def summarize_rows(question: str, rows: list[dict[str, Any]]) -> str:
    """Create an insightful textual summary from result rows."""
    if not rows:
        return "No matching rows were found."

    # For small result sets, try LLM-powered insights
    try:
        rows_preview = rows[:20]
        user_prompt = f"Question: {question}\n\nResults ({len(rows)} rows):\n{json.dumps(rows_preview, default=str, indent=2)}"
        return complete(
            system=INSIGHT_SYSTEM,
            user=user_prompt,
            temperature=0.3,
            max_tokens=512,
        )
    except Exception:
        pass

    # Fallback to simple formatting
    first = rows[0]
    if len(rows) == 1:
        parts = [f"{key}={value}" for key, value in list(first.items())[:4]]
        return f"Answer for '{question}': " + ", ".join(parts)

    preview = ", ".join(f"{k}={v}" for k, v in list(first.items())[:3])
    return f"Found {len(rows)} rows. Top result: {preview}"
