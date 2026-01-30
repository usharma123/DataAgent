"""
Data Agent
==========

A self-learning data agent that provides insights, not just query results.

The agent uses TWO separate knowledge bases:
1. Knowledge - Static, curated (table schemas, validated queries, business rules)
2. Learnings - Dynamic, discovered (query fixes, corrections, type gotchas)

The 6 Layers of Context:
1. Table Metadata - knowledge/tables/
2. Human Annotations - knowledge/business/
3. Query Patterns - knowledge/queries/
4. Institutional Knowledge - MCP connectors (optional)
5. Learnings - Discovered patterns (separate knowledge base)
6. Runtime Context - introspect_schema tool

Usage:
    python -m da

See README.md for full documentation.
"""

from da.agent import data_agent, data_agent_knowledge, data_agent_learnings

__all__ = [
    "data_agent",
    "data_agent_knowledge",
    "data_agent_learnings",
]

__version__ = "1.0.0"
