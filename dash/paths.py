"""Path constants."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
VAULT_DIR = Path(__file__).parent
KNOWLEDGE_DIR = VAULT_DIR / "knowledge"
TABLES_DIR = KNOWLEDGE_DIR / "tables"
BUSINESS_DIR = KNOWLEDGE_DIR / "business"
QUERIES_DIR = KNOWLEDGE_DIR / "queries"
