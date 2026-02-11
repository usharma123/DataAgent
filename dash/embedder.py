"""Embedding abstraction — local-first with optional OpenAI fallback.

Default: FastEmbed (BAAI/bge-small-en-v1.5), no API key needed.
Fallback: OpenAI text-embedding-3-small if OPENAI_API_KEY is set and local is disabled.
"""

from os import getenv

_fastembed_model = None


def _get_fastembed():
    global _fastembed_model
    if _fastembed_model is None:
        from fastembed import TextEmbedding

        model_name = getenv("VAULT_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
        _fastembed_model = TextEmbedding(model_name=model_name)
    return _fastembed_model


def embed_text(text: str) -> list[float]:
    """Embed a single text string and return a dense vector."""
    backend = getenv("VAULT_EMBED_BACKEND", "local").strip().lower()

    if backend == "openai":
        return _openai_embed(text)
    return _local_embed(text)


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts."""
    backend = getenv("VAULT_EMBED_BACKEND", "local").strip().lower()

    if backend == "openai":
        return [_openai_embed(t) for t in texts]
    return _local_embed_batch(texts)


def get_dimensions() -> int:
    """Return the embedding dimension for the active backend."""
    backend = getenv("VAULT_EMBED_BACKEND", "local").strip().lower()
    if backend == "openai":
        return 1536
    model = _get_fastembed()
    # FastEmbed models expose embedding dimension via a quick test
    test = list(model.embed(["test"]))[0]
    return len(test)


def _local_embed(text: str) -> list[float]:
    model = _get_fastembed()
    embeddings = list(model.embed([text]))
    return embeddings[0].tolist()


def _local_embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _get_fastembed()
    return [emb.tolist() for emb in model.embed(texts)]


def _openai_embed(text: str) -> list[float]:
    import openai

    client = openai.OpenAI()
    response = client.embeddings.create(
        model=getenv("VAULT_OPENAI_EMBED_MODEL", "text-embedding-3-small"),
        input=text,
    )
    return response.data[0].embedding
