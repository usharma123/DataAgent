# CLAUDE.md

## Project Overview

Vault is a self-learning personal data agent that indexes your iMessages, Gmail, and local files, then answers questions with cited evidence. It also includes a SQL data agent that delivers **insights, not just query results**, grounded in 6 layers of context. Inspired by [OpenAI's in-house data agent](https://openai.com/index/inside-our-in-house-data-agent/).

## Structure

```
dash/                     # Python package (module name)
├── paths.py              # Path constants
├── llm.py                # Model-agnostic LLM calls (litellm)
├── embedder.py           # Local embeddings (FastEmbed)
├── vectordb.py           # pgvector hybrid search wrapper
├── knowledge/            # Knowledge files (tables, queries, business rules)
│   ├── tables/           # Table metadata JSON files
│   ├── queries/          # Validated SQL queries
│   └── business/         # Business rules and metrics
├── context/
│   ├── semantic_model.py # Layer 1: Table usage
│   └── business_rules.py # Layer 2: Business rules
├── native/               # SQL data agent runtime
│   ├── orchestrator.py   # Query → SQL → Execute → Insight
│   ├── sql_drafter.py    # LLM-powered SQL generation
│   ├── insights.py       # LLM-powered result interpretation
│   └── store.py          # Run telemetry persistence
├── personal/             # Personal data agent runtime
│   ├── orchestrator.py   # Question → Retrieve → Cite → Answer
│   ├── memory.py         # Memory lifecycle management
│   ├── learning.py       # Reflection engine
│   ├── watcher.py        # Real-time file watcher (FSEvents)
│   └── connectors/       # Data source connectors
│       ├── gmail.py      # Gmail (OAuth)
│       ├── imessage.py   # iMessage (local SQLite)
│       ├── files.py      # Local files
│       └── slack.py      # Slack
├── tools/
│   ├── introspect.py     # Runtime schema inspection
│   └── save_query.py     # Save validated queries
├── scripts/
│   ├── load_data.py      # Load F1 sample data
│   └── load_knowledge.py # Load knowledge files
└── evals/
    ├── test_cases.py     # Test cases with golden SQL
    ├── grader.py         # LLM-based response grader
    └── run_evals.py      # Run evaluations

app/
├── main.py               # FastAPI entry point + file watcher lifecycle

db/
├── session.py            # PostgreSQL session factory (SQLAlchemy)
└── url.py                # Database URL builder
```

## Commands

```bash
./scripts/venv_setup.sh && source .venv/bin/activate
./scripts/format.sh      # Format code
./scripts/validate.sh    # Lint + type check
python -m dash           # CLI mode (/sql and /ask modes)

# Docker
docker compose up -d --build
curl http://localhost:8000/health

# Data & Knowledge
python -m dash.scripts.load_data       # Load F1 sample data
python -m dash.scripts.load_knowledge  # Load knowledge into vector DB
```

## Architecture

**No agent framework** — custom orchestration with FastAPI + litellm + fastembed.

**Two runtimes:**
- `dash/native/` — SQL data agent (query → SQL → execute → insight)
- `dash/personal/` — Personal data agent (iMessage, Gmail, files → retrieve → cite → answer)

**Two learning systems:**

| System | What It Stores | How It Evolves |
|--------|---------------|----------------|
| **Knowledge** | Validated queries, table metadata, business rules | Curated by you + Vault |
| **Memory** | Error patterns, user preferences, source quirks | Discovered automatically via reflection engine |

## Key Technologies

| Component | Technology |
|-----------|-----------|
| LLM | litellm (model-agnostic: gpt-4o, claude, ollama, etc.) |
| Embeddings | FastEmbed (BAAI/bge-small-en-v1.5, local, free) |
| Vector DB | pgvector (Postgres extension, hybrid search) |
| API | FastAPI |
| Database | PostgreSQL 17 + SQLAlchemy |
| File Watch | watchdog (macOS FSEvents) |
| Containers | Docker Compose (pgvector/pgvector:pg17 + python:3.12-slim) |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes* | OpenAI API key |
| `VAULT_LLM_MODEL` | No | LLM model (default: gpt-4o) |
| `VAULT_EMBED_BACKEND` | No | `local` (default) or `openai` |
| `GMAIL_CLIENT_ID` | No | Gmail OAuth client ID |
| `GMAIL_CLIENT_SECRET` | No | Gmail OAuth client secret |
| `GMAIL_REFRESH_TOKEN` | No | Gmail OAuth refresh token |
| `SLACK_USER_TOKEN` | No | Slack user token |
| `IMESSAGE_DB_PATH` | No | iMessage DB path |
| `VAULT_FILES_SCAN_DIRS` | No | Comma-separated dirs to watch |
| `DB_*` | No | Database config |

*At least one LLM API key required.

## Data Connectors

- **iMessage**: reads `~/Library/Messages/chat.db` (macOS Full Disk Access required)
- **Gmail**: OAuth refresh token flow
- **Slack**: xoxp- user token
- **Files**: auto-scans ~/Documents, ~/Desktop, ~/Downloads with real-time file watcher
