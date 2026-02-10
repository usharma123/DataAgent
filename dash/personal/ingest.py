"""Shared ingestion helpers for personal connectors."""

from datetime import UTC, datetime

from dash.personal.store import PersonalStore
from dash.personal.vector import LocalVectorEncoder


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[str]:
    """Chunk text content for retrieval."""
    content = " ".join(text.split())
    if len(content) <= chunk_size:
        return [content] if content else []

    chunks: list[str] = []
    start = 0
    while start < len(content):
        end = min(len(content), start + chunk_size)
        chunk = content[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(content):
            break
        start = max(0, end - overlap)
    return chunks


def ingest_document(
    *,
    store: PersonalStore,
    encoder: LocalVectorEncoder,
    payload: dict,
    body_text: str,
) -> tuple[int, int]:
    """Normalize body text into chunks + vectors and upsert into local store."""
    chunks = chunk_text(body_text)
    vectors = [encoder.encode(chunk) for chunk in chunks]

    normalized_payload = {
        "doc_id": payload["doc_id"],
        "source": payload["source"],
        "external_id": payload.get("external_id", payload["doc_id"]),
        "thread_id": payload.get("thread_id"),
        "account_id": payload.get("account_id"),
        "title": payload.get("title"),
        "body_text": body_text[:20000],
        "author": payload.get("author"),
        "participants": payload.get("participants", []),
        "timestamp_utc": payload.get("timestamp_utc") or datetime.now(UTC),
        "deep_link": payload.get("deep_link"),
        "metadata": payload.get("metadata", {}),
        "checksum": payload.get("checksum"),
    }
    return store.upsert_document(normalized_payload, chunks, vectors)
