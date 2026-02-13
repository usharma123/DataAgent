"""
Database URL
===========

Build database connection URL from environment variables.
"""

import logging
from os import getenv
from urllib.parse import quote

logger = logging.getLogger(__name__)

REQUIRED_VARS = ["DB_USER", "DB_PASS", "DB_DATABASE"]


def _validate_env() -> None:
    """Log warning for missing optional vars, raise for required."""
    missing = [v for v in REQUIRED_VARS if not getenv(v)]
    if missing:
        logger.warning("Missing recommended env vars: %s", missing)


def build_db_url() -> str | None:
    """Build database URL from environment variables.
    
    Returns None if required DB_PASS is not set (no hardcoded fallback).
    """
    _validate_env()
    
    driver = getenv("DB_DRIVER", "postgresql+psycopg")
    user = getenv("DB_USER", "")
    password = quote(getenv("DB_PASS", ""), safe="")
    host = getenv("DB_HOST", "localhost")
    port = getenv("DB_PORT", "5432")
    database = getenv("DB_DATABASE", "ai")

    if not password:
        return None
    return f"{driver}://{user}:{password}@{host}:{port}/{database}"


db_url = build_db_url()
