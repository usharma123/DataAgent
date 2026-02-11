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


def bulk_ingest(
    *,
    store: PersonalStore,
    encoder: LocalVectorEncoder,
    items: list[tuple[dict, str]],
) -> tuple[int, int]:
    """Bulk ingest multiple documents in a single transaction.

    Each item is (payload, body_text). Returns (docs_created, chunks_created).
    """
    # Phase 1: chunk all documents, collect texts for batch encoding
    doc_chunks: list[tuple[dict, list[str]]] = []
    all_chunk_texts: list[str] = []
    chunk_offsets: list[tuple[int, int]] = []  # (start_idx, count) per doc

    for payload, body_text in items:
        body_text = body_text.replace("\x00", "")
        text_chunks = chunk_text(body_text)
        start = len(all_chunk_texts)
        all_chunk_texts.extend(text_chunks)
        chunk_offsets.append((start, len(text_chunks)))
        normalized = {
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
        doc_chunks.append((normalized, text_chunks))

    # Phase 2: batch encode all chunks at once (much faster than per-chunk)
    all_vectors = encoder.encode_batch(all_chunk_texts) if all_chunk_texts else []

    # Phase 3: distribute vectors back to documents
    prepared: list[tuple[dict, list[str], list[list[float]]]] = []
    for i, (normalized, text_chunks) in enumerate(doc_chunks):
        start, count = chunk_offsets[i]
        vectors = all_vectors[start : start + count]
        prepared.append((normalized, text_chunks, vectors))

    return store.bulk_upsert_documents(prepared)


def ingest_document(
    *,
    store: PersonalStore,
    encoder: LocalVectorEncoder,
    payload: dict,
    body_text: str,
) -> tuple[int, int]:
    """Normalize body text into chunks + vectors and upsert into local store."""
    # PostgreSQL text fields cannot contain NUL (0x00) bytes
    body_text = body_text.replace("\x00", "")
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
