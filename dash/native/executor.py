"""Safe SQL execution for native Dash."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from time import perf_counter
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from dash.native.guardrails import SqlGuardrailConfig, load_sql_guardrail_config


@dataclass(frozen=True)
class SqlExecutionResult:
    """Execution output for one SQL query."""

    rows: list[dict[str, Any]]
    row_count: int
    duration_ms: int


class SqlExecutionError(RuntimeError):
    """SQL execution failed."""


class SqlExecutor:
    """Executes read-only SQL with timeout and JSON-safe row serialization."""

    def __init__(self, database_url: str, guardrail_config: SqlGuardrailConfig | None = None):
        self._engine = create_engine(database_url, pool_pre_ping=True)
        self._guardrail_config = guardrail_config or load_sql_guardrail_config()

    def execute(self, sql: str) -> SqlExecutionResult:
        """Execute SQL and return serialized rows."""
        started = perf_counter()
        try:
            with self._engine.begin() as conn:
                if conn.dialect.name == "postgresql":
                    conn.execute(
                        text(f"SET LOCAL statement_timeout = {self._guardrail_config.statement_timeout_ms}")
                    )
                result = conn.execute(text(sql))
                columns = list(result.keys())
                rows = [
                    {column: _serialize_value(value) for column, value in zip(columns, row)}
                    for row in result.fetchall()
                ]
        except SQLAlchemyError as exc:
            message = str(getattr(exc, "orig", exc))
            raise SqlExecutionError(message) from exc

        duration_ms = int((perf_counter() - started) * 1000)
        return SqlExecutionResult(rows=rows, row_count=len(rows), duration_ms=duration_ms)


def _serialize_value(value: Any) -> Any:
    """Convert SQL values into JSON-safe primitives."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)
