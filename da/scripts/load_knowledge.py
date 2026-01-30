"""
Load Knowledge - Loads table metadata, queries, and business rules into knowledge base.

Usage: python -m da.scripts.load_knowledge
"""

from da.paths import KNOWLEDGE_DIR

if __name__ == "__main__":
    from da.agent import data_agent_knowledge

    print(f"Loading knowledge from: {KNOWLEDGE_DIR}\n")

    for subdir in ["tables", "queries", "business"]:
        path = KNOWLEDGE_DIR / subdir
        if not path.exists():
            print(f"  {subdir}/: (not found)")
            continue

        files = [f for f in path.iterdir() if f.is_file() and not f.name.startswith(".")]
        print(f"  {subdir}/: {len(files)} files")

        if files:
            data_agent_knowledge.insert(name=f"knowledge-{subdir}", path=str(path))

    print("\nDone!")
