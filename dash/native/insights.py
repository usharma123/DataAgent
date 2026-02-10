"""Human-readable response synthesis for query results."""

from typing import Any


def summarize_rows(question: str, rows: list[dict[str, Any]]) -> str:
    """Create a compact textual insight from result rows."""
    if not rows:
        return "No matching rows were found."

    first = rows[0]
    if len(rows) == 1:
        parts = [f"{key}={value}" for key, value in list(first.items())[:4]]
        return f"Answer for '{question}': " + ", ".join(parts)

    preview = ", ".join(f"{k}={v}" for k, v in list(first.items())[:3])
    return f"Found {len(rows)} rows. Top result: {preview}"
