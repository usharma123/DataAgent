"""
Vault API
=========

FastAPI entry point for the Vault data agent.

Run:
    python -m app.main
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import logging
from contextlib import asynccontextmanager
from os import getenv

import uvicorn
from fastapi import FastAPI

from dash.native import native_router
from dash.personal import personal_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background services on boot, clean up on shutdown."""
    # Start file watcher
    from dash.personal.runtime import get_personal_store
    from dash.personal.watcher import start_file_watcher, stop_file_watcher

    try:
        store = get_personal_store()
        start_file_watcher(store)
        logger.info("File watcher started")
    except Exception:
        logger.warning("File watcher failed to start", exc_info=True)

    yield

    # Shutdown
    stop_file_watcher()
    logger.info("File watcher stopped")


app = FastAPI(
    title="Vault",
    description="Self-learning personal data agent API",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(native_router)
app.include_router(personal_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "engine": "native"}


if __name__ == "__main__":
    reload = getenv("RUNTIME_ENV", "prd") == "dev"
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(getenv("PORT", "8000")),
        reload=reload,
    )
