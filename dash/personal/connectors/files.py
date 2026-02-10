"""Local files connector for allowlist-based ingestion."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from dash.personal.connectors.base import BaseConnector, SyncResult
from dash.personal.ingest import ingest_document
from dash.personal.store import PersonalStore
from dash.personal.vector import LocalVectorEncoder

_SUPPORTED_FILE_SUFFIXES = {".txt", ".md", ".csv", ".json", ".log", ".pdf"}


class FilesConnector(BaseConnector):
    """Indexes allowlisted files into local document/chunk tables."""

    source = "files"

    def __init__(self, store: PersonalStore, encoder: LocalVectorEncoder):
        self._store = store
        self._encoder = encoder

    def sync(self, *, full: bool = False) -> SyncResult:
        """Sync allowlisted files and write local embeddings."""
        _ = full
        allowlist = self._store.list_file_allowlist()
        documents = 0
        chunks = 0

        for raw_path in allowlist:
            base = Path(raw_path).expanduser()
            if not base.exists():
                continue
            paths = [base] if base.is_file() else list(base.rglob("*"))
            for path in paths:
                if not path.is_file():
                    continue
                if path.suffix.lower() not in _SUPPORTED_FILE_SUFFIXES:
                    continue

                text = _read_file_text(path)
                if not text.strip():
                    continue

                checksum = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
                doc_id = f"files:{checksum[:32]}"
                created_docs, created_chunks = ingest_document(
                    store=self._store,
                    encoder=self._encoder,
                    payload={
                        "doc_id": doc_id,
                        "source": self.source,
                        "external_id": str(path),
                        "thread_id": None,
                        "account_id": "local",
                        "title": path.name,
                        "author": None,
                        "participants": [],
                        "timestamp_utc": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
                        "deep_link": str(path),
                        "metadata": {"path": str(path), "size": path.stat().st_size, "suffix": path.suffix.lower()},
                        "checksum": checksum,
                    },
                    body_text=text,
                )
                documents += created_docs
                chunks += created_chunks

        cursor = {"synced_at": datetime.now(UTC).isoformat(), "indexed_paths": len(allowlist)}
        return SyncResult(documents=documents, chunks=chunks, message="files sync completed", cursor=cursor)


def _read_file_text(path: Path) -> str:
    """Read text/PDF content in a dependency-light way."""
    try:
        if path.suffix.lower() != ".pdf":
            return path.read_text(errors="ignore")
        raw = path.read_bytes()
        return raw.decode("latin-1", errors="ignore")
    except OSError:
        return ""
