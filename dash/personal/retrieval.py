"""Hybrid retrieval helpers for personal data ask runs."""

import math
import re
import json
from dataclasses import dataclass
from datetime import datetime

from dash.personal.store import PersonalStore
from dash.personal.vector import LocalVectorEncoder, cosine_similarity

_TOKEN_RE = re.compile(r"[a-z0-9_]+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "which",
    "who",
    "with",
    "when",
    "where",
    "show",
}


@dataclass(frozen=True)
class RetrievedChunk:
    """Ranked chunk candidate."""

    chunk_id: str
    source: str
    text: str
    title: str | None
    author: str | None
    timestamp_utc: datetime | None
    deep_link: str | None
    score: float


class PersonalRetriever:
    """Simple hybrid retriever using lexical overlap and recency weighting."""

    def __init__(self, store: PersonalStore):
        self._store = store
        self._encoder = LocalVectorEncoder()

    def retrieve(
        self,
        *,
        question: str,
        source_filters: list[str],
        time_from: datetime | None,
        time_to: datetime | None,
        top_k: int,
    ) -> list[RetrievedChunk]:
        """Retrieve top chunks for a question."""
        question_tokens = tokenize(question)
        if not question_tokens:
            return []
        question_vector = self._encoder.encode(question)

        candidates = self._store.list_chunks(
            source_filters=source_filters,
            time_from=time_from,
            time_to=time_to,
            limit=max(200, top_k * 20),
        )

        scored: list[RetrievedChunk] = []
        for row in candidates:
            chunk_tokens = tokenize(row["text"])
            if not chunk_tokens:
                continue
            overlap = len(question_tokens & chunk_tokens)
            embedding = _parse_embedding(row.get("embedding_json"))
            vector_score = cosine_similarity(question_vector, embedding) if embedding else 0.0
            if overlap == 0 and vector_score <= 0:
                continue
            lexical = overlap / max(1, len(question_tokens)) if overlap > 0 else 0.0
            density = overlap / max(1, len(chunk_tokens))
            score = (
                (0.55 * lexical)
                + (0.25 * max(0.0, vector_score))
                + (0.15 * density)
                + (0.05 * _recency_boost(row.get("timestamp_utc")))
            )
            scored.append(
                RetrievedChunk(
                    chunk_id=str(row["chunk_id"]),
                    source=str(row["source"]),
                    text=str(row["text"]),
                    title=(str(row["title"]) if row.get("title") else None),
                    author=(str(row["author"]) if row.get("author") else None),
                    timestamp_utc=row.get("timestamp_utc"),
                    deep_link=(str(row["deep_link"]) if row.get("deep_link") else None),
                    score=max(0.0, min(1.0, score)),
                )
            )

        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]


def tokenize(text: str) -> set[str]:
    """Convert free text into normalized tokens."""
    tokens = {match for match in _TOKEN_RE.findall(text.lower()) if len(match) > 1}
    return {token for token in tokens if token not in _STOP_WORDS}


def _recency_boost(value: datetime | None) -> float:
    """Return bounded recency signal in [0,1]."""
    if value is None:
        return 0.0
    delta_days = abs((datetime.now(value.tzinfo) - value).days)
    return math.exp(-(delta_days / 30))


def _parse_embedding(raw: object) -> list[float] | None:
    if not raw:
        return None
    if isinstance(raw, list):
        return [float(value) for value in raw]
    if not isinstance(raw, str):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    vector: list[float] = []
    for item in payload:
        try:
            vector.append(float(item))
        except (TypeError, ValueError):
            return None
    return vector
