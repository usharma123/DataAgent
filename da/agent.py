"""
Data Agent
==========

A self-learning data agent inspired by OpenAI's internal data agent.

The agent uses TWO types of knowledge bases:

1. KNOWLEDGE (static, curated):
   - Table metadata and schemas
   - Validated SQL query patterns
   - Business rules and definitions
   → Search this FIRST for table info, query patterns, data quality notes

2. LEARNINGS (dynamic, discovered):
   - Patterns discovered through interaction
   - Query fixes and corrections
   - Type gotchas and workarounds
   → Search this when queries fail or to avoid past mistakes
   → Save here when discovering new patterns

The 6 Layers of Context:
1. Table Metadata - Schema info from knowledge/tables/
2. Human Annotations - Business rules from knowledge/business/
3. Query Patterns - Validated SQL from knowledge/queries/
4. Institutional Knowledge - External context via MCP (optional)
5. Learnings - Discovered patterns (separate from knowledge)
6. Runtime Context - Live schema inspection via introspect_schema tool
"""

from os import getenv

from agno.agent import Agent
from agno.knowledge import Knowledge
from agno.knowledge.embedder.openai import OpenAIEmbedder
from agno.models.openai import OpenAIResponses
from agno.tools.reasoning import ReasoningTools
from agno.tools.sql import SQLTools
from agno.vectordb.pgvector import PgVector, SearchType

from da.context.business_rules import BUSINESS_CONTEXT
from da.context.semantic_model import SEMANTIC_MODEL_STR
from da.tools import (
    analyze_results,
    create_introspect_schema_tool,
    create_learnings_tools,
    create_save_validated_query_tool,
)
from db import db_url, get_postgres_db

# ============================================================================
# Database & Knowledge Bases
# ============================================================================

# Database for storing agent sessions
agent_db = get_postgres_db()

# KNOWLEDGE: Static, curated information (table schemas, validated queries, business rules)
data_agent_knowledge = Knowledge(
    name="Data Agent Knowledge",
    vector_db=PgVector(
        db_url=db_url,
        table_name="data_agent_knowledge",
        search_type=SearchType.hybrid,
        embedder=OpenAIEmbedder(id="text-embedding-3-small"),
    ),
    contents_db=get_postgres_db(contents_table="data_agent_knowledge_contents"),
    max_results=10,
)

# LEARNINGS: Dynamic, discovered patterns (query fixes, corrections, gotchas)
data_agent_learnings = Knowledge(
    name="Data Agent Learnings",
    vector_db=PgVector(
        db_url=db_url,
        table_name="data_agent_learnings",
        search_type=SearchType.hybrid,
        embedder=OpenAIEmbedder(id="text-embedding-3-small"),
    ),
    contents_db=get_postgres_db(contents_table="data_agent_learnings_contents"),
    max_results=5,
)

# ============================================================================
# Create Tools
# ============================================================================

# Knowledge tools (save validated queries)
save_validated_query = create_save_validated_query_tool(data_agent_knowledge)

# Learnings tools (search/save discovered patterns)
search_learnings, save_learning = create_learnings_tools(data_agent_learnings)

# Runtime schema inspection (Layer 6)
introspect_schema = create_introspect_schema_tool(db_url)

# ============================================================================
# Instructions
# ============================================================================

INSTRUCTIONS = f"""\
You are a Data Agent with access to a PostgreSQL database.
Your goal is to help users get **insights** from data, not just raw query results.

You have TWO knowledge systems:
- **Knowledge**: Curated facts (table schemas, validated queries, business rules)
- **Learnings**: Patterns you've discovered (query fixes, type gotchas, corrections)

---

## WORKFLOW

### Step 1: SEARCH KNOWLEDGE
Before writing ANY SQL, search your knowledge base:
- Look for validated query patterns for similar questions
- Check table metadata and data quality notes
- Review business rules that might apply

### Step 2: SEARCH LEARNINGS
Check if you've encountered similar issues before:
- Past query fixes and corrections
- Type gotchas you've discovered
- Patterns that worked well

### Step 3: IDENTIFY TABLES
Using the semantic model below, identify relevant tables.
For detailed column information, use `introspect_schema`.

### Step 4: WRITE AND EXECUTE SQL
Follow these rules:
- Use LIMIT 50 by default
- Never use SELECT * - specify columns explicitly
- Include ORDER BY for top-N queries
- Never run destructive queries (DROP, DELETE, UPDATE, INSERT)

### Step 5: HANDLE ERRORS
If a query fails or returns unexpected results:
1. Check `search_learnings` for similar past issues
2. Use `introspect_schema` to verify column types
3. Fix the query and try again
4. **SAVE THE FIX** using `save_learning` so you don't repeat the mistake

### Step 6: PROVIDE INSIGHTS
Don't just return data - provide value:
- Summarize key findings
- Explain what the numbers mean
- Suggest follow-up questions

### Step 7: SAVE SUCCESSFUL QUERIES
After a validated query works well:
- Offer to save it using `save_validated_query`
- This adds it to your knowledge for future similar questions

---

## WHEN TO SAVE LEARNINGS

**ALWAYS save a learning when:**
- A query fails due to a type mismatch (e.g., position is TEXT not INTEGER)
- You discover a date/time parsing requirement
- A user corrects your interpretation
- You find a workaround for a data quality issue

**Check for duplicates FIRST** by calling `search_learnings` before saving.

**Example learnings to save:**
- "Position column in drivers_championship is TEXT - use string comparison '1' not integer 1"
- "Date column in race_wins needs TO_DATE(date, 'DD Mon YYYY') for year extraction"
- "Fastest laps table uses 'Venue' not 'circuit' for track names"

---

## SEMANTIC MODEL (Tables Overview)

{SEMANTIC_MODEL_STR}

For detailed column types, use `introspect_schema(table_name='...')`.

---

{BUSINESS_CONTEXT}

---

## TOOLS SUMMARY

| Tool | Purpose |
|------|---------|
| `search_learnings` | Find past fixes and patterns (check BEFORE queries) |
| `save_learning` | Save discovered patterns (ALWAYS after fixing errors) |
| `save_validated_query` | Save successful queries to knowledge |
| `introspect_schema` | Get detailed column types at runtime |
| `analyze_results` | Generate insights from query results |
"""

# ============================================================================
# Build Tools List
# ============================================================================

tools: list = [
    # SQL execution
    SQLTools(db_url=db_url),
    # Reasoning
    ReasoningTools(add_instructions=True),
    # Knowledge tools
    save_validated_query,
    # Learnings tools
    search_learnings,
    save_learning,
    # Analysis
    analyze_results,
    # Runtime introspection (Layer 6)
    introspect_schema,
]

# Add MCP tools for external knowledge (Layer 4) if configured
exa_api_key = getenv("EXA_API_KEY")
if exa_api_key:
    from agno.tools.mcp import MCPTools

    exa_url = f"https://mcp.exa.ai/mcp?exaApiKey={exa_api_key}&tools=web_search_exa"
    tools.append(MCPTools(url=exa_url))

# ============================================================================
# Create Agent
# ============================================================================

data_agent = Agent(
    id="data-agent",
    name="Data Agent",
    model=OpenAIResponses(id="gpt-5.2"),
    db=agent_db,
    # Knowledge (static - table schemas, validated queries)
    knowledge=data_agent_knowledge,
    search_knowledge=True,
    instructions=INSTRUCTIONS,
    tools=tools,
    # Context settings
    add_datetime_to_context=True,
    add_history_to_context=True,
    read_chat_history=True,
    num_history_runs=5,
    read_tool_call_history=True,
    # Output
    markdown=True,
)

# ============================================================================
# CLI Entry Point
# ============================================================================

if __name__ == "__main__":
    data_agent.cli_app(stream=True)
