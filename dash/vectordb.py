"""Thin pgvector wrapper for hybrid search (vector + tsvector).

Direct pgvector wrapper using SQLAlchemy.
"""

from datetime import UTC, datetime
from hashlib import md5

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
    select,
    text,
)
from sqlalchemy.engine import Engine

from dash.embedder import embed_text, get_dimensions


class VaultVectorStore:
    """Hybrid vector + full-text search over pgvector."""

    def __init__(
        self,
        *,
        database_url: str,
        table_name: str = "vault_knowledge",
        schema: str = "public",
        content_language: str = "english",
    ):
        self._engine: Engine = create_engine(database_url, pool_pre_ping=True)
        self._table_name = table_name
        self._schema = schema
        self._content_language = content_language
        self._dimensions = get_dimensions()
        self._metadata = MetaData(schema=schema)
        self._table = self._define_table()
        self._ensure_schema()

    def _define_table(self) -> Table:
        return Table(
            self._table_name,
            self._metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("content_hash", String(64), unique=True, nullable=False),
            Column("name", String(255)),
            Column("title", String(512)),
            Column("content", Text, nullable=False),
            Column("embedding", Vector(self._dimensions)),
            Column("tsvector_content", Text),  # stored generated tsvector
            Column("meta_json", Text),
            Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(UTC)),
            Column("updated_at", DateTime(timezone=True), default=lambda: datetime.now(UTC)),
            extend_existing=True,
        )

    def _ensure_schema(self) -> None:
        with self._engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        self._metadata.create_all(self._engine)
        # Create GIN index on tsvector for full-text search
        idx_name = f"idx_{self._table_name}_tsvector"
        gin_sql = (
            f"CREATE INDEX IF NOT EXISTS {idx_name} "
            f"ON {self._schema}.{self._table_name} "
            f"USING GIN (to_tsvector('{self._content_language}', content))"
        )
        hnsw_name = f"idx_{self._table_name}_hnsw"
        hnsw_sql = (
            f"CREATE INDEX IF NOT EXISTS {hnsw_name} "
            f"ON {self._schema}.{self._table_name} "
            f"USING hnsw (embedding vector_cosine_ops)"
        )
        with self._engine.begin() as conn:
            conn.execute(text(gin_sql))
            conn.execute(text(hnsw_sql))

    def insert(self, *, name: str, title: str, content: str, meta_json: str = "{}") -> None:
        """Insert a document, skip if content hash already exists."""
        content_hash = md5(content.encode()).hexdigest()
        with self._engine.begin() as conn:
            exists = conn.execute(
                select(self._table.c.id).where(self._table.c.content_hash == content_hash)
            ).scalar_one_or_none()
            if exists is not None:
                return
            embedding = embed_text(content)
            conn.execute(
                self._table.insert().values(
                    content_hash=content_hash,
                    name=name,
                    title=title,
                    content=content,
                    embedding=embedding,
                    meta_json=meta_json,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )

    def search(self, query: str, *, limit: int = 10) -> list[dict]:
        """Hybrid search: combine vector similarity and full-text ranking."""
        query_embedding = embed_text(query)
        lang = self._content_language
        t = self._table

        # Vector similarity (cosine distance → similarity)
        vector_dist = t.c.embedding.cosine_distance(query_embedding).label("vector_dist")

        # Full-text rank
        ts_query = func.plainto_tsquery(lang, query)
        ts_rank = func.ts_rank(
            func.to_tsvector(lang, t.c.content), ts_query
        ).label("ts_rank")

        # Combined score: RRF-style fusion
        # vector_score = 1 / (1 + distance), ts_score = ts_rank
        stmt = (
            select(
                t.c.id,
                t.c.name,
                t.c.title,
                t.c.content,
                t.c.meta_json,
                vector_dist,
                ts_rank,
            )
            .order_by(
                # Sort by combined RRF: lower distance is better, higher ts_rank is better
                (vector_dist - ts_rank).asc()
            )
            .limit(limit)
        )

        with self._engine.begin() as conn:
            rows = conn.execute(stmt).mappings().all()

        results = []
        for row in rows:
            dist = float(row["vector_dist"]) if row["vector_dist"] is not None else 1.0
            ts = float(row["ts_rank"]) if row["ts_rank"] is not None else 0.0
            score = (1.0 / (1.0 + dist)) * 0.6 + ts * 0.4
            results.append({
                "id": row["id"],
                "name": row["name"],
                "title": row["title"],
                "content": row["content"],
                "meta_json": row["meta_json"],
                "score": score,
            })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results

    def drop(self) -> None:
        """Drop the vector table."""
        self._table.drop(self._engine, checkfirst=True)

    def recreate(self) -> None:
        """Drop and recreate the table."""
        self.drop()
        self._metadata.create_all(self._engine)
        self._ensure_schema()
