"""
Load Knowledge - Loads table metadata, queries, and business rules into vector store.

Usage:
    python -m dash.scripts.load_knowledge             # Upsert (update existing)
    python -m dash.scripts.load_knowledge --recreate   # Drop and reload all
"""

import argparse
import json

from dash.paths import KNOWLEDGE_DIR
from dash.vectordb import VaultVectorStore
from db.url import db_url


def load_knowledge(recreate: bool = False) -> None:
    store = VaultVectorStore(database_url=db_url, table_name="dash_knowledge")

    if recreate:
        print("Recreating knowledge base (dropping existing data)...\n")
        store.recreate()

    print(f"Loading knowledge from: {KNOWLEDGE_DIR}\n")

    for subdir in ["tables", "queries", "business"]:
        path = KNOWLEDGE_DIR / subdir
        if not path.exists():
            print(f"  {subdir}/: (not found)")
            continue

        files = [f for f in path.iterdir() if f.is_file() and not f.name.startswith(".")]
        print(f"  {subdir}/: {len(files)} files")

        for filepath in files:
            content = filepath.read_text(encoding="utf-8").strip()
            if not content:
                continue

            name = f"knowledge-{subdir}"
            title = filepath.stem

            if filepath.suffix == ".json":
                try:
                    meta = json.loads(content)
                    title = meta.get("table_name", meta.get("name", title))
                except json.JSONDecodeError:
                    pass

            store.insert(
                name=name,
                title=title,
                content=content,
                meta_json=json.dumps({"source": subdir, "file": filepath.name}),
            )

    print("\nDone!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load knowledge into vector database")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop existing knowledge and reload from scratch",
    )
    args = parser.parse_args()
    load_knowledge(recreate=args.recreate)
