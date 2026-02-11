"""Vector encoding and text utilities for personal retrieval.

Encoding is backed by fastembed (BAAI/bge-small-en-v1.5) for semantic embeddings.
Lexical helpers (tokenize, normalize, cosine) are kept for hybrid scoring fallback.
"""

import re
import unicodedata

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
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


class LocalVectorEncoder:
    """Semantic embedding encoder backed by fastembed."""

    def __init__(self, dimensions: int | None = None, *, skip: bool | None = None):
        # dimensions parameter kept for backward compat; actual dims come from model.
        self._dim_cache: int | None = None
        if skip is not None:
            self._skip = skip
        else:
            from os import getenv
            self._skip = getenv("VAULT_SKIP_EMBEDDINGS", "").strip() == "1"

    @property
    def dimensions(self) -> int:
        """Embedding dimension (determined by the model)."""
        if self._dim_cache is None:
            from dash.embedder import get_dimensions

            self._dim_cache = get_dimensions()
        return self._dim_cache

    def encode(self, text: str) -> list[float]:
        """Encode a single text into a dense semantic vector."""
        if self._skip:
            return []
        from dash.embedder import embed_text

        return embed_text(text)

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """Encode multiple texts in one batch (much faster than per-text encode)."""
        if self._skip:
            return [[] for _ in texts]
        from dash.embedder import embed_batch

        return embed_batch(texts)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity for two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))


def normalize_text(text: str) -> str:
    """Normalize text for stable lexical feature extraction."""
    lowered = unicodedata.normalize("NFKC", str(text)).lower()
    without_accents = "".join(
        char for char in unicodedata.normalize("NFKD", lowered) if not unicodedata.combining(char)
    )
    compact = re.sub(r"[^a-z0-9]+", " ", without_accents)
    return " ".join(compact.split())


def tokenize_terms(text: str) -> list[str]:
    """Tokenize normalized text into useful terms."""
    normalized = normalize_text(text)
    return [token for token in _TOKEN_RE.findall(normalized) if len(token) > 1 and token not in _STOP_WORDS]
