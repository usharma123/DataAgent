"""
Vault API
=========

FastAPI entry point for the Vault data agent.

Run:
    python -m app.main
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from os import getenv
from threading import Lock

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from dash.native import native_router
from dash.personal import personal_router
from dash.router import vault_router

logger = logging.getLogger(__name__)

_RATE_LIMIT = int(getenv("VAULT_RATE_LIMIT", "100"))
_RATE_WINDOW_SECONDS = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter using sliding window."""

    def __init__(self, app, rate_limit: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.rate_limit = rate_limit
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def _clean_old_requests(self, key: str, now: float) -> None:
        cutoff = now - self.window_seconds
        self._requests[key] = [ts for ts in self._requests[key] if ts > cutoff]

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ["/health", "/docs", "/openapi.json"]:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        with self._lock:
            self._clean_old_requests(client_ip, now)
            if len(self._requests[client_ip]) >= self.rate_limit:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Max {self.rate_limit} requests per {self.window_seconds}s."
                )
            self._requests[client_ip].append(now)

        return await call_next(request)


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

app.add_middleware(RateLimitMiddleware, rate_limit=_RATE_LIMIT, window_seconds=_RATE_WINDOW_SECONDS)

app.include_router(native_router)
app.include_router(personal_router)
app.include_router(vault_router)


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
