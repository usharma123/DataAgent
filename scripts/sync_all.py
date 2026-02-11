#!/usr/bin/env python3
"""Full data sync — indexes Gmail, iMessage, and local files into shared PostgreSQL.

Usage:
    python scripts/sync_all.py                    # All sources, incremental
    python scripts/sync_all.py --full             # Full re-sync (ignores cursors)
    python scripts/sync_all.py --source gmail     # Single source only
    python scripts/sync_all.py --source imessage --full
"""

import argparse
import logging
import os
import sys
import time

# Ensure project root is importable
_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _PROJECT_ROOT)

# Load .env from project root (Gmail/Slack credentials, DB config, etc.)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_PROJECT_ROOT, ".env"), override=False)
except ImportError:
    pass

from dash.personal.runtime import get_personal_store
from dash.personal.sync import PersonalSyncService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sync_all")

ALL_SOURCES = ["gmail", "imessage", "files"]


def _sync_gmail(svc: PersonalSyncService, *, full: bool) -> None:
    """Sync Gmail with extended page limit for bulk ingestion."""
    original_max_pages = os.environ.get("GMAIL_SYNC_MAX_PAGES")
    original_query = os.environ.get("GMAIL_SYNC_QUERY")

    # Override defaults for bulk sync: 100 pages × 100 = up to 10K messages
    os.environ["GMAIL_SYNC_MAX_PAGES"] = os.environ.get("GMAIL_SYNC_MAX_PAGES", "100")
    if full and not original_query:
        os.environ["GMAIL_SYNC_QUERY"] = "newer_than:30d"

    try:
        docs, chunks, msg = svc.sync_source(source="gmail", full=full)
        logger.info("gmail: %d docs, %d chunks — %s", docs, chunks, msg)
    finally:
        # Restore original env
        if original_max_pages is None:
            os.environ.pop("GMAIL_SYNC_MAX_PAGES", None)
        else:
            os.environ["GMAIL_SYNC_MAX_PAGES"] = original_max_pages
        if original_query is None:
            os.environ.pop("GMAIL_SYNC_QUERY", None)
        else:
            os.environ["GMAIL_SYNC_QUERY"] = original_query


def _sync_imessage(svc: PersonalSyncService, *, full: bool) -> None:
    """Sync iMessage in batches until all messages are consumed."""
    batch_size = 20000
    os.environ["IMESSAGE_SYNC_LIMIT"] = str(batch_size)

    total_docs = 0
    total_chunks = 0
    batch_num = 0
    prev_rowid = -1

    while True:
        batch_num += 1
        docs, chunks, msg = svc.sync_source(source="imessage", full=(full and batch_num == 1))
        total_docs += docs
        total_chunks += chunks

        # Check cursor progress — stop when rowid stops advancing
        source_row = svc._store.get_source("imessage")
        cursor = (source_row or {}).get("cursor", {})
        current_rowid = int((cursor if isinstance(cursor, dict) else {}).get("last_rowid", 0) or 0)

        logger.info(
            "imessage batch %d: %d docs, %d chunks (rowid=%d, total: %d docs, %d chunks)",
            batch_num, docs, chunks, current_rowid, total_docs, total_chunks,
        )

        if current_rowid <= prev_rowid:
            break  # No new rows consumed
        prev_rowid = current_rowid

    logger.info("imessage: %d total docs, %d total chunks", total_docs, total_chunks)


def _sync_files(svc: PersonalSyncService, *, full: bool) -> None:
    """Sync local files (incremental by mtime)."""
    docs, chunks, msg = svc.sync_source(source="files", full=full)
    logger.info("files: %d docs, %d chunks — %s", docs, chunks, msg)


_SYNC_FNS = {
    "gmail": _sync_gmail,
    "imessage": _sync_imessage,
    "files": _sync_files,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync all personal data sources into PostgreSQL")
    parser.add_argument("--full", action="store_true", help="Full re-sync (ignore saved cursors)")
    parser.add_argument("--source", choices=ALL_SOURCES, help="Sync only this source")
    args = parser.parse_args()

    sources = [args.source] if args.source else ALL_SOURCES
    store = get_personal_store()
    svc = PersonalSyncService(store=store)

    logger.info("Starting sync: sources=%s full=%s", sources, args.full)
    t0 = time.monotonic()

    for source in sources:
        logger.info("── %s ──", source)
        try:
            _SYNC_FNS[source](svc, full=args.full)
        except Exception:
            logger.exception("Failed to sync %s", source)

    elapsed = time.monotonic() - t0
    logger.info("Sync complete in %.1fs", elapsed)


if __name__ == "__main__":
    main()
