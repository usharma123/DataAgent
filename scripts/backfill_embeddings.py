#!/usr/bin/env python3
"""Phase 2: Backfill pgvector embeddings for personal_chunks.

Reads chunks missing embeddings from PostgreSQL, encodes via OpenAI batch API,
and writes the vectors back. Runs sequentially to respect rate limits.

Usage:
    python scripts/backfill_embeddings.py                # all sources
    python scripts/backfill_embeddings.py --source files  # one source
    python scripts/backfill_embeddings.py --batch 2000    # custom batch size
"""

import argparse
import json
import logging
import os
import sys
import time

_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_PROJECT_ROOT, ".env"), override=False)
except ImportError:
    pass

from sqlalchemy import create_engine, text

from dash.embedder import embed_batch, get_dimensions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill")


def backfill(*, engine, source: str | None, batch_size: int) -> None:
    dims = get_dimensions()
    logger.info("Embedding dims: %d", dims)

    where = "WHERE embedding IS NULL"
    params: dict = {}
    if source:
        where += " AND source = :source"
        params["source"] = source

    with engine.begin() as conn:
        total = conn.execute(
            text(f"SELECT COUNT(*) FROM personal_chunks {where}"), params
        ).scalar_one()
    logger.info("Chunks to backfill: %s", f"{total:,}")

    if total == 0:
        return

    processed = 0
    t0 = time.monotonic()

    while processed < total:
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"SELECT chunk_id, text FROM personal_chunks "
                    f"{where} "
                    f"ORDER BY chunk_id LIMIT :limit"
                ),
                {**params, "limit": batch_size},
            ).fetchall()

        if not rows:
            break

        chunk_ids = [r[0] for r in rows]
        texts = [r[1] for r in rows]

        try:
            vectors = embed_batch(texts)
        except Exception as exc:
            logger.error("Embed batch failed: %s — retrying in 30s", exc)
            time.sleep(30)
            continue

        # Write embeddings back
        with engine.begin() as conn:
            for cid, vec in zip(chunk_ids, vectors):
                if not vec:
                    continue
                vec_json = json.dumps(vec)
                conn.execute(
                    text(
                        "UPDATE personal_chunks "
                        "SET embedding_json = :vec_json, "
                        "    embedding = :vec_json::vector "
                        "WHERE chunk_id = :cid"
                    ),
                    {"cid": cid, "vec_json": vec_json},
                )

        processed += len(rows)
        elapsed = time.monotonic() - t0
        rate = processed / elapsed * 60 if elapsed > 0 else 0
        eta_min = (total - processed) / rate if rate > 0 else 0
        logger.info(
            "%s / %s (%.1f%%) — %.0f chunks/min — ETA %.0f min",
            f"{processed:,}", f"{total:,}",
            processed / total * 100, rate, eta_min,
        )

    elapsed = time.monotonic() - t0
    logger.info("Done: %s chunks in %.1fs", f"{processed:,}", elapsed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill embeddings for personal_chunks")
    parser.add_argument("--source", choices=["gmail", "imessage", "files"], help="Only backfill this source")
    parser.add_argument("--batch", type=int, default=500, help="Chunks per API batch (default 500)")
    args = parser.parse_args()

    from db.url import build_db_url
    db_url = os.getenv("VAULT_PERSONAL_DB_URL", "").strip() or build_db_url()
    engine = create_engine(db_url, pool_pre_ping=True)

    logger.info("Backend: %s", os.getenv("VAULT_EMBED_BACKEND", "local"))
    logger.info("Source filter: %s", args.source or "all")

    backfill(engine=engine, source=args.source, batch_size=args.batch)


if __name__ == "__main__":
    main()
