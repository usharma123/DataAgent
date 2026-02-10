"""Dash package exports."""

from typing import Any

__all__ = ["dash", "reasoning_dash", "dash_knowledge", "dash_learnings"]


def __getattr__(name: str) -> Any:
    """Lazily load Agno-based agent objects to keep native modules importable."""
    if name in __all__:
        from dash.agents import dash, dash_knowledge, dash_learnings, reasoning_dash

        exports = {
            "dash": dash,
            "reasoning_dash": reasoning_dash,
            "dash_knowledge": dash_knowledge,
            "dash_learnings": dash_learnings,
        }
        return exports[name]
    raise AttributeError(f"module 'dash' has no attribute '{name}'")
