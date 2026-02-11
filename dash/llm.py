"""Model-agnostic LLM calling via litellm.

Supports OpenAI, Anthropic, Ollama, and any litellm-compatible provider.
Configure via VAULT_LLM_MODEL env var (default: gpt-4o).
"""

from os import getenv

import litellm


def get_model() -> str:
    """Return the configured LLM model identifier."""
    return getenv("VAULT_LLM_MODEL", "gpt-4o")


def complete(
    *,
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    """Simple completion: system + user message → string response."""
    response = litellm.completion(
        model=model or get_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""
