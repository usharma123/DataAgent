"""
Database Module
===============

Database connection utilities.
"""

from db.url import db_url

__all__ = [
    "db_url",
    "get_postgres_db",
]


def __getattr__(name: str):
    """Lazily import Agno-backed DB helpers for native-mode compatibility."""
    if name == "get_postgres_db":
        from db.session import get_postgres_db

        return get_postgres_db
    raise AttributeError(f"module 'db' has no attribute '{name}'")
