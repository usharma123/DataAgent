"""SQL guardrails for the native Vault runtime."""

import re
from dataclasses import dataclass
from os import getenv

FORBIDDEN_SQL_KEYWORDS = (
    "alter",
    "call",
    "comment",
    "copy",
    "create",
    "delete",
    "drop",
    "grant",
    "insert",
    "merge",
    "reindex",
    "revoke",
    "truncate",
    "update",
    "vacuum",
)

_COMMENT_PATTERN = re.compile(r"--.*?$|/\*.*?\*/", flags=re.MULTILINE | re.DOTALL)
_LIMIT_PATTERN = re.compile(r"\blimit\s+(\d+)\b", flags=re.IGNORECASE)


class SqlGuardrailError(ValueError):
    """Raised when SQL violates safety constraints."""


@dataclass(frozen=True)
class SqlGuardrailConfig:
    """Runtime-configurable SQL safety limits."""

    default_limit: int = 50
    max_limit: int = 500
    max_sql_length: int = 20_000
    statement_timeout_ms: int = 15_000
    max_sql_attempts: int = 3


def load_sql_guardrail_config() -> SqlGuardrailConfig:
    """Load SQL guardrail configuration from environment variables."""
    return SqlGuardrailConfig(
        default_limit=_read_int("VAULT_SQL_DEFAULT_LIMIT", 50),
        max_limit=_read_int("VAULT_SQL_MAX_LIMIT", 500),
        max_sql_length=_read_int("VAULT_SQL_MAX_LENGTH", 20_000),
        statement_timeout_ms=_read_int("VAULT_SQL_TIMEOUT_MS", 15_000),
        max_sql_attempts=_read_int("VAULT_MAX_SQL_ATTEMPTS", 3),
    )


def validate_and_normalize_sql(sql: str, config: SqlGuardrailConfig | None = None) -> str:
    """Validate SQL against read-only constraints and apply a default LIMIT."""
    if config is None:
        config = load_sql_guardrail_config()

    if len(sql) > config.max_sql_length:
        raise SqlGuardrailError(
            f"SQL exceeds maximum length ({len(sql)} > {config.max_sql_length})."
        )

    cleaned = _strip_comments(sql).strip().rstrip(";")
    if not cleaned:
        raise SqlGuardrailError("SQL is empty after removing comments.")

    if ";" in cleaned:
        raise SqlGuardrailError("Only one SQL statement is allowed per request.")

    first_token = cleaned.split(maxsplit=1)[0].lower()
    if first_token not in {"select", "with"}:
        raise SqlGuardrailError("Only SELECT/WITH queries are allowed.")

    lowered = f" {cleaned.lower()} "
    for keyword in FORBIDDEN_SQL_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", lowered):
            raise SqlGuardrailError(f"Forbidden SQL keyword detected: {keyword}")

    limit_match = _LIMIT_PATTERN.search(cleaned)
    if limit_match:
        requested_limit = int(limit_match.group(1))
        if requested_limit > config.max_limit:
            raise SqlGuardrailError(
                f"Requested LIMIT {requested_limit} exceeds max_limit {config.max_limit}."
            )
        return cleaned

    return f"{cleaned}\nLIMIT {config.default_limit}"


def _strip_comments(sql: str) -> str:
    """Remove SQL comments so checks only inspect executable text."""
    return _COMMENT_PATTERN.sub("", sql)


def _read_int(name: str, default: int) -> int:
    """Parse positive integers from env vars with safe defaults."""
    raw = getenv(name)
    if raw is None:
        return default

    try:
        parsed = int(raw)
    except ValueError:
        return default

    return parsed if parsed > 0 else default

