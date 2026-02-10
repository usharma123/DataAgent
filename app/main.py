"""
Dash API
========

Deployment entry point for Dash.

Run:
    python -m app.main
"""

from os import getenv
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI

from dash.native import native_router
from dash.personal import personal_router

agent_os: Any | None = None
engine = getenv("DASH_ENGINE", "agno").strip().lower()

if engine == "native":
    app = FastAPI(title="Dash Native API")
else:
    from agno.os import AgentOS

    from dash.agents import dash, dash_knowledge, reasoning_dash
    from db import get_postgres_db

    agent_os = AgentOS(
        name="Dash",
        tracing=True,
        db=get_postgres_db(),
        agents=[dash, reasoning_dash],
        knowledge=[dash_knowledge],
        config=str(Path(__file__).parent / "config.yaml"),
    )
    app = agent_os.get_app()

app.include_router(native_router)
app.include_router(personal_router)

if __name__ == "__main__":
    reload = getenv("RUNTIME_ENV", "prd") == "dev"
    if agent_os is not None:
        agent_os.serve(app="main:app", reload=reload)
    else:
        uvicorn.run("app.main:app", host="0.0.0.0", port=int(getenv("PORT", "8000")), reload=reload)
