"""Local vector encoding utilities for personal retrieval.

This keeps all embedding computation and storage local.
"""

import math
import re
from os import getenv

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


class LocalVectorEncoder:
    """Deterministic local embedding encoder using hashing trick."""

    def __init__(self, dimensions: int | None = None):
        self._dimensions = dimensions or _read_positive_int("VAULT_PERSONAL_VECTOR_DIM", 256)

    @property
    def dimensions(self) -> int:
        """Configured embedding dimension."""
        return self._dimensions

    def encode(self, text: str) -> list[float]:
        """Encode text into normalized dense vector without external services."""
        vector = [0.0] * self._dimensions
        tokens = [token for token in _TOKEN_RE.findall(text.lower()) if len(token) > 1]
        if not tokens:
            return vector

        for token in tokens:
            bucket = hash(token) % self._dimensions
            sign = 1.0 if ((hash(token + "_s") & 1) == 0) else -1.0
            vector[bucket] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity for two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))


def _read_positive_int(name: str, default: int) -> int:
    raw = getenv(name)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return parsed if parsed > 0 else default
