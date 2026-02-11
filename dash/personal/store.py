"""Persistence layer for personal data agent runtime."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    and_,
    create_engine,
    delete,
    desc,
    func,
    insert,
    select,
    text,
)
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

personal_metadata = MetaData()

sources = Table(
    "personal_sources",
    personal_metadata,
    Column("source", String(32), primary_key=True),
    Column("connected", Boolean, nullable=False, default=False),
    Column("last_sync_at", DateTime(timezone=True), nullable=True),
    Column("cursor_json", Text, nullable=True),
)

documents = Table(
    "personal_documents",
    personal_metadata,
    Column("doc_id", String(128), primary_key=True),
    Column("source", String(32), nullable=False),
    Column("external_id", String(255), nullable=False),
    Column("thread_id", String(255), nullable=True),
    Column("account_id", String(255), nullable=True),
    Column("title", Text, nullable=True),
    Column("body_text", Text, nullable=False),
    Column("author", String(255), nullable=True),
    Column("participants_json", Text, nullable=True),
    Column("timestamp_utc", DateTime(timezone=True), nullable=True),
    Column("deep_link", Text, nullable=True),
    Column("metadata_json", Text, nullable=True),
    Column("checksum", String(128), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

chunks = Table(
    "personal_chunks",
    personal_metadata,
    Column("chunk_id", String(128), primary_key=True),
    Column("doc_id", String(128), ForeignKey("personal_documents.doc_id", ondelete="CASCADE"), nullable=False),
    Column("source", String(32), nullable=False),
    Column("chunk_index", Integer, nullable=False),
    Column("text", Text, nullable=False),
    Column("token_count", Integer, nullable=False),
    Column("embedding_json", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

citations = Table(
    "personal_citations",
    personal_metadata,
    Column("citation_id", String(64), primary_key=True),
    Column("run_id", String(64), nullable=False),
    Column("chunk_id", String(128), ForeignKey("personal_chunks.chunk_id", ondelete="CASCADE"), nullable=False),
    Column("rank", Integer, nullable=False),
    Column("score", Float, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

personal_query_runs = Table(
    "personal_query_runs",
    personal_metadata,
    Column("run_id", String(64), primary_key=True),
    Column("status", String(16), nullable=False),
    Column("question", Text, nullable=False),
    Column("user_id", String(128), nullable=True),
    Column("session_id", String(128), nullable=True),
    Column("answer", Text, nullable=True),
    Column("error", Text, nullable=True),
    Column("outcome_class", String(32), nullable=True),
    Column("retries", Integer, nullable=False, default=1),
    Column("missing_evidence_json", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

personal_feedback_events = Table(
    "personal_feedback_events",
    personal_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(64), nullable=False),
    Column("verdict", String(16), nullable=False),
    Column("comment", Text, nullable=True),
    Column("corrected_answer", Text, nullable=True),
    Column("corrected_filters_json", Text, nullable=True),
    Column("corrected_source_scope", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

memory_candidates = Table(
    "memory_candidates",
    personal_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(64), nullable=True),
    Column("kind", String(32), nullable=False),
    Column("scope", String(32), nullable=False),
    Column("title", String(255), nullable=False),
    Column("learning", Text, nullable=False),
    Column("confidence", Integer, nullable=False),
    Column("evidence_citation_ids_json", Text, nullable=True),
    Column("status", String(32), nullable=False),
    Column("metadata_json", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

memory_items = Table(
    "memory_items",
    personal_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("kind", String(32), nullable=False),
    Column("scope", String(32), nullable=False),
    Column("statement", Text, nullable=False),
    Column("activation_state", String(32), nullable=False),
    Column("confidence", Integer, nullable=False),
    Column("source", String(64), nullable=False),
    Column("supersedes_id", Integer, ForeignKey("memory_items.id"), nullable=True),
    Column("last_verified_at", DateTime(timezone=True), nullable=True),
    Column("expiry_at", DateTime(timezone=True), nullable=True),
    Column("metadata_json", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

memory_events = Table(
    "memory_events",
    personal_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("memory_item_id", Integer, ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=True),
    Column("memory_candidate_id", Integer, ForeignKey("memory_candidates.id", ondelete="CASCADE"), nullable=True),
    Column("event", String(32), nullable=False),
    Column("reason", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

memory_usage = Table(
    "memory_usage",
    personal_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(64), nullable=False),
    Column("memory_item_id", Integer, ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=False),
    Column("influence_score", Float, nullable=False),
    Column("applied", Boolean, nullable=False),
    Column("reason", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

memory_eval_runs = Table(
    "memory_eval_runs",
    personal_metadata,
    Column("run_id", String(64), primary_key=True),
    Column("status", String(16), nullable=False),
    Column("results_json", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

file_allowlist = Table(
    "file_allowlist",
    personal_metadata,
    Column("path", Text, primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


class PersonalStoreError(RuntimeError):
    """Storage operation failed."""


class PersonalStore:
    """Persistence API for personal data agent operations."""

    def __init__(self, database_url: str):
        self._engine = create_engine(database_url, pool_pre_ping=True)
        self._schema_ready = False
        self._has_pgvector = False

    def ensure_schema(self) -> None:
        """Create personal runtime tables if needed."""
        if self._schema_ready:
            return
        try:
            personal_metadata.create_all(self._engine, checkfirst=True)
            self._seed_sources_if_missing()
            self._setup_pgvector()
            self._schema_ready = True
        except SQLAlchemyError as exc:
            raise PersonalStoreError(f"Failed to create personal tables: {exc}") from exc

    def _setup_pgvector(self) -> None:
        """Add pgvector column and indexes if running on PostgreSQL."""
        dialect = self._engine.dialect.name
        if dialect != "postgresql":
            return
        try:
            from dash.embedder import get_dimensions

            dims = get_dimensions()
            with self._engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.execute(text(
                    f"ALTER TABLE personal_chunks "
                    f"ADD COLUMN IF NOT EXISTS embedding vector({dims})"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_personal_chunks_hnsw "
                    "ON personal_chunks USING hnsw (embedding vector_cosine_ops)"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_personal_chunks_gin "
                    "ON personal_chunks "
                    "USING GIN (to_tsvector('english', text))"
                ))
            self._has_pgvector = True
            logger.info("pgvector enabled for personal_chunks (dims=%d)", dims)
        except Exception as exc:
            logger.warning("pgvector setup skipped: %s", exc)
            self._has_pgvector = False

    def _seed_sources_if_missing(self) -> None:
        expected = ["gmail", "slack", "imessage", "files"]
        with self._engine.begin() as conn:
            existing = {
                row[0]
                for row in conn.execute(select(sources.c.source)).fetchall()
            }
            for source in expected:
                if source not in existing:
                    conn.execute(
                        insert(sources).values(
                            source=source,
                            connected=False,
                            last_sync_at=None,
                            cursor_json=None,
                        )
                    )

    def upsert_source(self, *, source: str, connected: bool, cursor: dict[str, Any] | None = None) -> None:
        """Create or update source connection metadata."""
        self.ensure_schema()
        now = datetime.now(UTC)
        payload = {
            "source": source,
            "connected": connected,
            "last_sync_at": now,
            "cursor_json": json.dumps(cursor) if cursor else None,
        }
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    sources.update()
                    .where(sources.c.source == source)
                    .values(**payload)
                )
                existing = conn.execute(
                    select(sources.c.source).where(sources.c.source == source)
                ).scalar_one_or_none()
                if existing is None:
                    conn.execute(insert(sources).values(**payload))
        except SQLAlchemyError as exc:
            raise PersonalStoreError(f"Failed to upsert source: {exc}") from exc

    def update_source_sync(self, *, source: str, cursor: dict[str, Any] | None = None) -> None:
        """Update source last sync timestamp and optional cursor."""
        self.ensure_schema()
        values: dict[str, Any] = {"last_sync_at": datetime.now(UTC)}
        if cursor is not None:
            values["cursor_json"] = json.dumps(cursor)
        try:
            with self._engine.begin() as conn:
                conn.execute(sources.update().where(sources.c.source == source).values(**values))
        except SQLAlchemyError as exc:
            raise PersonalStoreError(f"Failed to update source sync: {exc}") from exc

    def list_sources(self) -> list[dict[str, Any]]:
        """Return source status rows."""
        self.ensure_schema()
        try:
            with self._engine.begin() as conn:
                rows = conn.execute(select(sources)).mappings().all()
            result: list[dict[str, Any]] = []
            for row in rows:
                data = dict(row)
                raw_cursor = data.get("cursor_json")
                data["cursor"] = json.loads(raw_cursor) if raw_cursor else None
                data.pop("cursor_json", None)
                result.append(data)
            return sorted(result, key=lambda item: item["source"])
        except (SQLAlchemyError, json.JSONDecodeError) as exc:
            raise PersonalStoreError(f"Failed to list sources: {exc}") from exc

    def get_source(self, source: str) -> dict[str, Any] | None:
        """Return one source row with decoded cursor."""
        self.ensure_schema()
        stmt = select(sources).where(sources.c.source == source)
        try:
            with self._engine.begin() as conn:
                row = conn.execute(stmt).mappings().first()
            if row is None:
                return None
            payload = dict(row)
            raw_cursor = payload.get("cursor_json")
            payload["cursor"] = json.loads(raw_cursor) if raw_cursor else None
            payload.pop("cursor_json", None)
            return payload
        except (SQLAlchemyError, json.JSONDecodeError) as exc:
            raise PersonalStoreError(f"Failed to read source {source}: {exc}") from exc

    def create_query_run(
        self,
        *,
        run_id: str,
        question: str,
        user_id: str | None,
        session_id: str | None,
    ) -> None:
        """Insert personal query run."""
        self.ensure_schema()
        now = datetime.now(UTC)
        payload = {
            "run_id": run_id,
            "status": "accepted",
            "question": question,
            "user_id": user_id,
            "session_id": session_id,
            "created_at": now,
            "updated_at": now,
            "retries": 1,
        }
        try:
            with self._engine.begin() as conn:
                conn.execute(insert(personal_query_runs).values(**payload))
        except SQLAlchemyError as exc:
            raise PersonalStoreError(f"Failed to create personal run: {exc}") from exc

    def finalize_query_run(
        self,
        *,
        run_id: str,
        status: str,
        answer: str | None,
        error: str | None,
        outcome_class: str,
        retries: int,
        missing_evidence: list[str],
    ) -> None:
        """Complete run with output metadata."""
        self.ensure_schema()
        values = {
            "status": status,
            "answer": answer,
            "error": error,
            "outcome_class": outcome_class,
            "retries": retries,
            "missing_evidence_json": json.dumps(missing_evidence),
            "updated_at": datetime.now(UTC),
        }
        try:
            with self._engine.begin() as conn:
                result = conn.execute(
                    personal_query_runs.update().where(personal_query_runs.c.run_id == run_id).values(**values)
                )
                if result.rowcount == 0:
                    raise PersonalStoreError(f"Run {run_id} not found")
        except SQLAlchemyError as exc:
            raise PersonalStoreError(f"Failed to finalize personal run: {exc}") from exc

    def upsert_document(
        self,
        payload: dict[str, Any],
        chunk_texts: list[str],
        chunk_embeddings: list[list[float]] | None = None,
    ) -> tuple[int, int]:
        """Upsert one document and replace chunks."""
        self.ensure_schema()
        now = datetime.now(UTC)
        created_docs = 0
        created_chunks = 0
        doc_payload = {
            "doc_id": payload["doc_id"],
            "source": payload["source"],
            "external_id": payload.get("external_id", payload["doc_id"]),
            "thread_id": payload.get("thread_id"),
            "account_id": payload.get("account_id"),
            "title": payload.get("title"),
            "body_text": payload.get("body_text", ""),
            "author": payload.get("author"),
            "participants_json": json.dumps(payload.get("participants", [])),
            "timestamp_utc": payload.get("timestamp_utc"),
            "deep_link": payload.get("deep_link"),
            "metadata_json": json.dumps(payload.get("metadata", {})),
            "checksum": payload.get("checksum"),
            "updated_at": now,
        }
        try:
            with self._engine.begin() as conn:
                existing = conn.execute(
                    select(documents.c.doc_id).where(documents.c.doc_id == payload["doc_id"])
                ).scalar_one_or_none()
                if existing is None:
                    doc_payload["created_at"] = now
                    conn.execute(insert(documents).values(**doc_payload))
                    created_docs = 1
                else:
                    conn.execute(documents.update().where(documents.c.doc_id == payload["doc_id"]).values(**doc_payload))

                conn.execute(delete(chunks).where(chunks.c.doc_id == payload["doc_id"]))
                embeddings = chunk_embeddings or []
                for index, text_value in enumerate(chunk_texts):
                    chunk_id = f"{payload['doc_id']}:{index}"
                    embedding = embeddings[index] if index < len(embeddings) else None
                    conn.execute(
                        insert(chunks).values(
                            chunk_id=chunk_id,
                            doc_id=payload["doc_id"],
                            source=payload["source"],
                            chunk_index=index,
                            text=text_value,
                            token_count=max(1, len(text_value.split())),
                            embedding_json=json.dumps(embedding) if embedding else None,
                            created_at=now,
                        )
                    )
                    created_chunks += 1
        except (SQLAlchemyError, KeyError, TypeError, ValueError) as exc:
            raise PersonalStoreError(f"Failed to upsert personal document: {exc}") from exc

        return created_docs, created_chunks

    def bulk_upsert_documents(
        self,
        items: list[tuple[dict, list[str], list[list[float]]]],
    ) -> tuple[int, int]:
        """Bulk upsert documents + chunks in a single transaction.

        Each item is (payload, chunk_texts, chunk_embeddings).
        Returns (total_docs_created, total_chunks_created).
        """
        if not items:
            return 0, 0
        # Deduplicate by doc_id (keep last occurrence)
        seen: dict[str, int] = {}
        for idx, (payload, _, _) in enumerate(items):
            seen[payload["doc_id"]] = idx
        if len(seen) < len(items):
            items = [items[i] for i in sorted(seen.values())]
        self.ensure_schema()
        now = datetime.now(UTC)
        total_docs = 0
        total_chunks = 0

        try:
            with self._engine.begin() as conn:
                # 1. Fetch existing doc_ids in one query
                all_doc_ids = [item[0]["doc_id"] for item in items]
                existing_ids: set[str] = set()
                for batch_start in range(0, len(all_doc_ids), 500):
                    batch_ids = all_doc_ids[batch_start : batch_start + 500]
                    rows = conn.execute(
                        select(documents.c.doc_id).where(documents.c.doc_id.in_(batch_ids))
                    ).fetchall()
                    existing_ids.update(row[0] for row in rows)

                # 2. Separate into inserts vs updates
                doc_inserts: list[dict] = []
                doc_updates: list[tuple[str, dict]] = []
                for payload, _, _ in items:
                    doc_payload = {
                        "doc_id": payload["doc_id"],
                        "source": payload["source"],
                        "external_id": payload.get("external_id", payload["doc_id"]),
                        "thread_id": payload.get("thread_id"),
                        "account_id": payload.get("account_id"),
                        "title": payload.get("title"),
                        "body_text": payload.get("body_text", ""),
                        "author": payload.get("author"),
                        "participants_json": json.dumps(payload.get("participants", [])),
                        "timestamp_utc": payload.get("timestamp_utc"),
                        "deep_link": payload.get("deep_link"),
                        "metadata_json": json.dumps(payload.get("metadata", {})),
                        "checksum": payload.get("checksum"),
                        "updated_at": now,
                    }
                    if payload["doc_id"] not in existing_ids:
                        doc_payload["created_at"] = now
                        doc_inserts.append(doc_payload)
                        total_docs += 1
                    else:
                        doc_updates.append((payload["doc_id"], doc_payload))

                # 3. Bulk INSERT new documents
                if doc_inserts:
                    conn.execute(insert(documents), doc_inserts)

                # 4. Bulk UPDATE existing documents
                for doc_id, vals in doc_updates:
                    conn.execute(documents.update().where(documents.c.doc_id == doc_id).values(**vals))

                # 5. Bulk DELETE old chunks
                for batch_start in range(0, len(all_doc_ids), 500):
                    batch_ids = all_doc_ids[batch_start : batch_start + 500]
                    conn.execute(delete(chunks).where(chunks.c.doc_id.in_(batch_ids)))

                # 6. Bulk INSERT new chunks
                chunk_rows: list[dict] = []
                for payload, chunk_texts, chunk_embeddings in items:
                    embeddings = chunk_embeddings or []
                    for index, text_value in enumerate(chunk_texts):
                        embedding = embeddings[index] if index < len(embeddings) else None
                        chunk_rows.append({
                            "chunk_id": f"{payload['doc_id']}:{index}",
                            "doc_id": payload["doc_id"],
                            "source": payload["source"],
                            "chunk_index": index,
                            "text": text_value,
                            "token_count": max(1, len(text_value.split())),
                            "embedding_json": json.dumps(embedding) if embedding else None,
                            "created_at": now,
                        })
                if chunk_rows:
                    # Insert in batches of 1000 to avoid parameter limits
                    for batch_start in range(0, len(chunk_rows), 1000):
                        conn.execute(insert(chunks), chunk_rows[batch_start : batch_start + 1000])
                    total_chunks = len(chunk_rows)

                # 7. Populate pgvector embedding column from embedding_json
                if self._has_pgvector and chunk_rows:
                    chunk_ids = [row["chunk_id"] for row in chunk_rows if row.get("embedding_json")]
                    for batch_start in range(0, len(chunk_ids), 500):
                        batch_cids = chunk_ids[batch_start : batch_start + 500]
                        conn.execute(text(
                            "UPDATE personal_chunks "
                            "SET embedding = embedding_json::vector "
                            "WHERE chunk_id = ANY(:ids) AND embedding_json IS NOT NULL"
                        ), {"ids": batch_cids})

        except (SQLAlchemyError, KeyError, TypeError, ValueError) as exc:
            raise PersonalStoreError(f"Failed to bulk upsert documents: {exc}") from exc

        return total_docs, total_chunks

    def list_chunks(
        self,
        *,
        source_filters: list[str],
        time_from: datetime | None,
        time_to: datetime | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Return chunks joined with document metadata."""
        self.ensure_schema()
        stmt = (
            select(
                chunks.c.chunk_id,
                chunks.c.doc_id,
                chunks.c.source,
                chunks.c.text,
                chunks.c.chunk_index,
                chunks.c.embedding_json,
                documents.c.title,
                documents.c.author,
                documents.c.timestamp_utc,
                documents.c.deep_link,
            )
            .join(documents, documents.c.doc_id == chunks.c.doc_id)
            .order_by(documents.c.timestamp_utc.desc().nullslast(), chunks.c.chunk_index.asc())
            .limit(limit)
        )

        conditions = []
        if source_filters:
            conditions.append(chunks.c.source.in_(source_filters))
        if time_from is not None:
            conditions.append(documents.c.timestamp_utc >= time_from)
        if time_to is not None:
            conditions.append(documents.c.timestamp_utc <= time_to)
        if conditions:
            stmt = stmt.where(and_(*conditions))

        try:
            with self._engine.begin() as conn:
                rows = conn.execute(stmt).mappings().all()
            return [dict(row) for row in rows]
        except SQLAlchemyError as exc:
            raise PersonalStoreError(f"Failed to list chunks: {exc}") from exc

    @property
    def has_pgvector(self) -> bool:
        """Whether pgvector hybrid search is available."""
        return self._has_pgvector

    def vector_search(
        self,
        *,
        query_embedding: list[float],
        query_text: str,
        source_filters: list[str],
        time_from: datetime | None,
        time_to: datetime | None,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Hybrid pgvector + full-text search over personal_chunks.

        Uses HNSW index for vector similarity and GIN index for full-text ranking.
        Combines scores with RRF-style fusion. Only works on PostgreSQL with pgvector.
        """
        if not self._has_pgvector:
            raise PersonalStoreError("pgvector not available")
        self.ensure_schema()

        embedding_literal = "[" + ",".join(str(v) for v in query_embedding) + "]"

        where_clauses = ["c.embedding IS NOT NULL"]
        params: dict[str, Any] = {
            "query_text": query_text,
            "top_k": top_k,
        }

        if source_filters:
            where_clauses.append("c.source = ANY(:source_filters)")
            params["source_filters"] = source_filters
        if time_from is not None:
            where_clauses.append("d.timestamp_utc >= :time_from")
            params["time_from"] = time_from
        if time_to is not None:
            where_clauses.append("d.timestamp_utc <= :time_to")
            params["time_to"] = time_to

        where_sql = " AND ".join(where_clauses)

        sql = f"""
            SELECT
                c.chunk_id,
                c.doc_id,
                c.source,
                c.text,
                c.chunk_index,
                d.title,
                d.author,
                d.timestamp_utc,
                d.deep_link,
                c.embedding <=> '{embedding_literal}'::vector AS vector_dist,
                ts_rank(
                    to_tsvector('english', c.text),
                    plainto_tsquery('english', :query_text)
                ) AS ts_rank
            FROM personal_chunks c
            JOIN personal_documents d ON d.doc_id = c.doc_id
            WHERE {where_sql}
            ORDER BY
                (c.embedding <=> '{embedding_literal}'::vector) - ts_rank ASC
            LIMIT :top_k
        """

        try:
            with self._engine.begin() as conn:
                rows = conn.execute(text(sql), params).mappings().all()

            results: list[dict[str, Any]] = []
            for row in rows:
                dist = float(row["vector_dist"]) if row["vector_dist"] is not None else 1.0
                ts = float(row["ts_rank"]) if row["ts_rank"] is not None else 0.0
                score = (1.0 / (1.0 + dist)) * 0.6 + ts * 0.4
                results.append({
                    "chunk_id": row["chunk_id"],
                    "doc_id": row["doc_id"],
                    "source": row["source"],
                    "text": row["text"],
                    "chunk_index": row["chunk_index"],
                    "title": row["title"],
                    "author": row["author"],
                    "timestamp_utc": row["timestamp_utc"],
                    "deep_link": row["deep_link"],
                    "score": max(0.0, min(1.0, score)),
                })
            results.sort(key=lambda r: r["score"], reverse=True)
            return results
        except SQLAlchemyError as exc:
            raise PersonalStoreError(f"Vector search failed: {exc}") from exc

    def save_citations(self, *, run_id: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Persist citations for a run and return citation payloads."""
        self.ensure_schema()
        now = datetime.now(UTC)
        result: list[dict[str, Any]] = []

        try:
            with self._engine.begin() as conn:
                for index, item in enumerate(items, start=1):
                    citation_id = f"c_{run_id[:12]}_{index}"
                    conn.execute(
                        insert(citations).values(
                            citation_id=citation_id,
                            run_id=run_id,
                            chunk_id=item["chunk_id"],
                            rank=index,
                            score=float(item.get("score", 0.0)),
                            created_at=now,
                        )
                    )
                    result.append(
                        {
                            "citation_id": citation_id,
                            "source": item["source"],
                            "title": item.get("title"),
                            "snippet": item["text"][:400],
                            "author": item.get("author"),
                            "timestamp": item.get("timestamp_utc"),
                            "deep_link": item.get("deep_link"),
                            "confidence": max(0.0, min(1.0, float(item.get("score", 0.0)))),
                            "chunk_id": item["chunk_id"],
                        }
                    )
        except (SQLAlchemyError, KeyError, TypeError, ValueError) as exc:
            raise PersonalStoreError(f"Failed to save citations: {exc}") from exc

        return result

    def get_citation(self, citation_id: str) -> dict[str, Any] | None:
        """Load one citation and its linked chunk/document metadata."""
        self.ensure_schema()
        stmt = (
            select(
                citations.c.citation_id,
                citations.c.run_id,
                citations.c.rank,
                citations.c.score,
                chunks.c.chunk_id,
                chunks.c.source,
                chunks.c.text,
                documents.c.title,
                documents.c.author,
                documents.c.timestamp_utc,
                documents.c.deep_link,
            )
            .join(chunks, citations.c.chunk_id == chunks.c.chunk_id)
            .join(documents, chunks.c.doc_id == documents.c.doc_id)
            .where(citations.c.citation_id == citation_id)
        )
        try:
            with self._engine.begin() as conn:
                row = conn.execute(stmt).mappings().first()
            return dict(row) if row else None
        except SQLAlchemyError as exc:
            raise PersonalStoreError(f"Failed to read citation: {exc}") from exc

    def list_citations_for_run(self, run_id: str) -> list[str]:
        """Return citation ids generated for a run."""
        self.ensure_schema()
        stmt = (
            select(citations.c.citation_id)
            .where(citations.c.run_id == run_id)
            .order_by(citations.c.rank.asc())
        )
        try:
            with self._engine.begin() as conn:
                rows = conn.execute(stmt).fetchall()
            return [str(row[0]) for row in rows]
        except SQLAlchemyError as exc:
            raise PersonalStoreError(f"Failed to list citations for run: {exc}") from exc

    def create_feedback_event(
        self,
        *,
        run_id: str,
        verdict: str,
        comment: str | None,
        corrected_answer: str | None,
        corrected_filters: list[str],
        corrected_source_scope: str | None,
    ) -> int:
        """Persist personal feedback and return event id."""
        self.ensure_schema()
        payload = {
            "run_id": run_id,
            "verdict": verdict,
            "comment": comment,
            "corrected_answer": corrected_answer,
            "corrected_filters_json": json.dumps(corrected_filters),
            "corrected_source_scope": corrected_source_scope,
            "created_at": datetime.now(UTC),
        }
        try:
            with self._engine.begin() as conn:
                result = conn.execute(insert(personal_feedback_events).values(**payload))
                return int(result.inserted_primary_key[0])
        except (SQLAlchemyError, ValueError, TypeError) as exc:
            raise PersonalStoreError(f"Failed to save feedback event: {exc}") from exc

    def create_memory_candidate(
        self,
        *,
        run_id: str | None,
        kind: str,
        scope: str,
        title: str,
        learning: str,
        confidence: int,
        evidence_citation_ids: list[str],
        status: str = "proposed",
        metadata_dict: dict[str, Any] | None = None,
    ) -> int:
        """Persist memory candidate and return id."""
        self.ensure_schema()
        payload = {
            "run_id": run_id,
            "kind": kind,
            "scope": scope,
            "title": title,
            "learning": learning,
            "confidence": confidence,
            "evidence_citation_ids_json": json.dumps(evidence_citation_ids),
            "status": status,
            "metadata_json": json.dumps(metadata_dict or {}),
            "created_at": datetime.now(UTC),
        }
        try:
            with self._engine.begin() as conn:
                result = conn.execute(insert(memory_candidates).values(**payload))
                return int(result.inserted_primary_key[0])
        except (SQLAlchemyError, ValueError, TypeError) as exc:
            raise PersonalStoreError(f"Failed to create memory candidate: {exc}") from exc

    def list_memory_candidates(self, *, status: str | None = "proposed") -> list[dict[str, Any]]:
        """List memory candidates optionally filtered by status."""
        self.ensure_schema()
        stmt = select(memory_candidates).order_by(desc(memory_candidates.c.created_at))
        if status is not None:
            stmt = stmt.where(memory_candidates.c.status == status)
        try:
            with self._engine.begin() as conn:
                rows = conn.execute(stmt).mappings().all()
            return [self._deserialize_memory_candidate(row) for row in rows]
        except (SQLAlchemyError, json.JSONDecodeError) as exc:
            raise PersonalStoreError(f"Failed to list memory candidates: {exc}") from exc

    def get_memory_candidate(self, candidate_id: int) -> dict[str, Any] | None:
        """Return one memory candidate row."""
        self.ensure_schema()
        stmt = select(memory_candidates).where(memory_candidates.c.id == candidate_id)
        try:
            with self._engine.begin() as conn:
                row = conn.execute(stmt).mappings().first()
            return self._deserialize_memory_candidate(row) if row else None
        except (SQLAlchemyError, json.JSONDecodeError) as exc:
            raise PersonalStoreError(f"Failed to read memory candidate: {exc}") from exc

    def mark_memory_candidate(self, *, candidate_id: int, status: str) -> None:
        """Update memory candidate status."""
        self.ensure_schema()
        try:
            with self._engine.begin() as conn:
                result = conn.execute(
                    memory_candidates.update().where(memory_candidates.c.id == candidate_id).values(status=status)
                )
                if result.rowcount == 0:
                    raise PersonalStoreError(f"Memory candidate {candidate_id} not found")
        except SQLAlchemyError as exc:
            raise PersonalStoreError(f"Failed to update memory candidate: {exc}") from exc

    def create_memory_item(
        self,
        *,
        kind: str,
        scope: str,
        statement: str,
        confidence: int,
        source: str,
        supersedes_id: int | None,
        metadata_dict: dict[str, Any] | None,
        activation_state: str = "active",
    ) -> int:
        """Create memory item and return id."""
        self.ensure_schema()
        payload = {
            "kind": kind,
            "scope": scope,
            "statement": statement,
            "activation_state": activation_state,
            "confidence": confidence,
            "source": source,
            "supersedes_id": supersedes_id,
            "last_verified_at": datetime.now(UTC),
            "expiry_at": None,
            "metadata_json": json.dumps(metadata_dict or {}),
            "created_at": datetime.now(UTC),
        }
        try:
            with self._engine.begin() as conn:
                result = conn.execute(insert(memory_items).values(**payload))
                return int(result.inserted_primary_key[0])
        except (SQLAlchemyError, ValueError, TypeError) as exc:
            raise PersonalStoreError(f"Failed to create memory item: {exc}") from exc

    def list_memory_items(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        """List memory items."""
        self.ensure_schema()
        stmt = select(memory_items).order_by(desc(memory_items.c.created_at))
        if active_only:
            stmt = stmt.where(memory_items.c.activation_state == "active")
        try:
            with self._engine.begin() as conn:
                rows = conn.execute(stmt).mappings().all()
            return [self._deserialize_memory_item(row) for row in rows]
        except (SQLAlchemyError, json.JSONDecodeError) as exc:
            raise PersonalStoreError(f"Failed to list memory items: {exc}") from exc

    def get_memory_item(self, item_id: int) -> dict[str, Any] | None:
        """Get memory item by id."""
        self.ensure_schema()
        stmt = select(memory_items).where(memory_items.c.id == item_id)
        try:
            with self._engine.begin() as conn:
                row = conn.execute(stmt).mappings().first()
            return self._deserialize_memory_item(row) if row else None
        except (SQLAlchemyError, json.JSONDecodeError) as exc:
            raise PersonalStoreError(f"Failed to read memory item: {exc}") from exc

    def update_memory_item(
        self,
        *,
        item_id: int,
        activation_state: str,
        supersedes_id: int | None = None,
        expiry_at: datetime | None = None,
    ) -> None:
        """Update memory item state metadata."""
        self.ensure_schema()
        values: dict[str, Any] = {
            "activation_state": activation_state,
            "last_verified_at": datetime.now(UTC),
        }
        if supersedes_id is not None:
            values["supersedes_id"] = supersedes_id
        if expiry_at is not None:
            values["expiry_at"] = expiry_at

        try:
            with self._engine.begin() as conn:
                result = conn.execute(memory_items.update().where(memory_items.c.id == item_id).values(**values))
                if result.rowcount == 0:
                    raise PersonalStoreError(f"Memory item {item_id} not found")
        except SQLAlchemyError as exc:
            raise PersonalStoreError(f"Failed to update memory item: {exc}") from exc

    def create_memory_event(
        self,
        *,
        event: str,
        reason: str | None,
        memory_item_id: int | None = None,
        memory_candidate_id: int | None = None,
    ) -> int:
        """Create memory event entry."""
        self.ensure_schema()
        payload = {
            "memory_item_id": memory_item_id,
            "memory_candidate_id": memory_candidate_id,
            "event": event,
            "reason": reason,
            "created_at": datetime.now(UTC),
        }
        try:
            with self._engine.begin() as conn:
                result = conn.execute(insert(memory_events).values(**payload))
                return int(result.inserted_primary_key[0])
        except (SQLAlchemyError, ValueError, TypeError) as exc:
            raise PersonalStoreError(f"Failed to create memory event: {exc}") from exc

    def record_memory_usage(
        self,
        *,
        run_id: str,
        memory_item_id: int,
        influence_score: float,
        applied: bool,
        reason: str,
    ) -> None:
        """Persist memory usage trace for a run."""
        self.ensure_schema()
        payload = {
            "run_id": run_id,
            "memory_item_id": memory_item_id,
            "influence_score": float(influence_score),
            "applied": applied,
            "reason": reason,
            "created_at": datetime.now(UTC),
        }
        try:
            with self._engine.begin() as conn:
                conn.execute(insert(memory_usage).values(**payload))
        except SQLAlchemyError as exc:
            raise PersonalStoreError(f"Failed to record memory usage: {exc}") from exc

    def list_memory_usage(self, *, run_id: str) -> list[dict[str, Any]]:
        """List memory usage traces for a run."""
        self.ensure_schema()
        stmt = (
            select(memory_usage.c.memory_item_id, memory_usage.c.influence_score, memory_usage.c.applied, memory_usage.c.reason)
            .where(memory_usage.c.run_id == run_id)
            .order_by(memory_usage.c.id.asc())
        )
        try:
            with self._engine.begin() as conn:
                rows = conn.execute(stmt).mappings().all()
            return [dict(row) for row in rows]
        except SQLAlchemyError as exc:
            raise PersonalStoreError(f"Failed to list memory usage: {exc}") from exc

    def create_memory_eval_run(self, *, run_id: str, status: str, payload: dict[str, Any]) -> None:
        """Persist memory eval snapshot."""
        self.ensure_schema()
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    insert(memory_eval_runs).values(
                        run_id=run_id,
                        status=status,
                        results_json=json.dumps(payload),
                        created_at=datetime.now(UTC),
                    )
                )
        except (SQLAlchemyError, TypeError, ValueError) as exc:
            raise PersonalStoreError(f"Failed to save memory eval: {exc}") from exc

    def memory_eval_window(self, *, lookback_days: int = 7) -> dict[str, Any]:
        """Compute windowed memory quality metrics."""
        self.ensure_schema()
        try:
            with self._engine.begin() as conn:
                total_runs = conn.execute(select(func.count()).select_from(personal_query_runs)).scalar_one()
                success_runs = conn.execute(
                    select(func.count()).select_from(personal_query_runs).where(personal_query_runs.c.status == "success")
                ).scalar_one()
                runs_with_memory = conn.execute(
                    select(func.count(func.distinct(memory_usage.c.run_id))).select_from(memory_usage)
                ).scalar_one()
                memory_applied = conn.execute(
                    select(func.count()).select_from(memory_usage).where(memory_usage.c.applied.is_(True))
                ).scalar_one()
                repeated_failures = conn.execute(
                    select(func.count())
                    .select_from(personal_query_runs)
                    .where(
                        and_(
                            personal_query_runs.c.status == "failed",
                            personal_query_runs.c.outcome_class.is_not(None),
                        )
                    )
                ).scalar_one()
                citation_total = conn.execute(select(func.count()).select_from(citations)).scalar_one()
                runs_with_citations = conn.execute(
                    select(func.count(func.distinct(citations.c.run_id))).select_from(citations)
                ).scalar_one()

            return {
                "total_runs": int(total_runs or 0),
                "success_runs": int(success_runs or 0),
                "runs_with_memory": int(runs_with_memory or 0),
                "memory_applied_events": int(memory_applied or 0),
                "repeated_failures": int(repeated_failures or 0),
                "citation_total": int(citation_total or 0),
                "runs_with_citations": int(runs_with_citations or 0),
            }
        except SQLAlchemyError as exc:
            raise PersonalStoreError(f"Failed to compute memory eval window: {exc}") from exc

    def replace_file_allowlist(self, paths: list[str]) -> None:
        """Replace allowlist paths for file source sync."""
        self.ensure_schema()
        now = datetime.now(UTC)
        cleaned = sorted({path.strip() for path in paths if path.strip()})
        try:
            with self._engine.begin() as conn:
                conn.execute(delete(file_allowlist))
                for path in cleaned:
                    conn.execute(insert(file_allowlist).values(path=path, created_at=now))
        except SQLAlchemyError as exc:
            raise PersonalStoreError(f"Failed to replace file allowlist: {exc}") from exc

    def list_file_allowlist(self) -> list[str]:
        """Read allowlisted file paths."""
        self.ensure_schema()
        stmt = select(file_allowlist.c.path).order_by(file_allowlist.c.path.asc())
        try:
            with self._engine.begin() as conn:
                rows = conn.execute(stmt).fetchall()
            return [str(row[0]) for row in rows]
        except SQLAlchemyError as exc:
            raise PersonalStoreError(f"Failed to read file allowlist: {exc}") from exc

    @staticmethod
    def _deserialize_memory_candidate(row: Any) -> dict[str, Any]:
        payload = dict(row)
        payload["evidence_citation_ids"] = json.loads(payload.pop("evidence_citation_ids_json") or "[]")
        payload["metadata"] = json.loads(payload.pop("metadata_json") or "{}")
        return payload

    @staticmethod
    def _deserialize_memory_item(row: Any) -> dict[str, Any]:
        payload = dict(row)
        payload["metadata"] = json.loads(payload.pop("metadata_json") or "{}")
        return payload
