"""
Database Session
================

Plain SQLAlchemy session factory.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from db.url import db_url

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine(database_url: str | None = None) -> Engine:
    """Return a process-wide SQLAlchemy engine (singleton for default URL)."""
    if database_url is not None:
        return create_engine(database_url, pool_pre_ping=True)

    global _engine
    if _engine is None:
        _engine = create_engine(db_url, pool_pre_ping=True)
    return _engine


def get_session(database_url: str | None = None) -> Session:
    """Create a new SQLAlchemy session."""
    if database_url is not None:
        factory = sessionmaker(bind=get_engine(database_url))
        return factory()

    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine())
    return _session_factory()


def ensure_pgvector_extension(database_url: str | None = None) -> None:
    """Create the pgvector extension if it does not exist."""
    engine = get_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
