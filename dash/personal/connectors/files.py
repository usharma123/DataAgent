"""Local files connector — scans home folder for useful documents and code."""

import hashlib
import logging
from datetime import UTC, datetime
from os import getenv
from pathlib import Path

from dash.personal.connectors.base import BaseConnector, SyncResult
from dash.personal.ingest import ingest_document
from dash.personal.store import PersonalStore
from dash.personal.vector import LocalVectorEncoder

logger = logging.getLogger(__name__)

# ── File types worth indexing ──────────────────────────────────────────────────

_DOC_SUFFIXES = {
    ".txt", ".md", ".markdown", ".rst", ".rtf",
    ".pdf",
    ".csv", ".tsv",
    ".json", ".yaml", ".yml", ".toml", ".xml",
    ".log", ".ini", ".cfg", ".conf",
    ".doc", ".docx", ".xls", ".xlsx", ".pptx",
    ".org", ".tex", ".bib",
    ".html", ".htm",
}

_CODE_SUFFIXES = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".kt", ".scala",
    ".c", ".cpp", ".h", ".hpp", ".cs",
    ".go", ".rs", ".rb", ".php",
    ".swift", ".m", ".mm",
    ".sh", ".bash", ".zsh", ".fish",
    ".sql", ".graphql",
    ".r", ".R", ".jl",
    ".lua", ".pl", ".pm",
    ".tf", ".hcl",
    ".proto",
    ".ipynb",
    ".makefile", ".cmake",
}

_SUPPORTED_SUFFIXES = _DOC_SUFFIXES | _CODE_SUFFIXES

# ── Directories to always skip ─────────────────────────────────────────────────

_SKIP_DIRS = {
    # System / OS
    ".Trash", "Library", ".cache", ".local", ".npm", ".nvm",
    ".cargo", ".rustup", ".gem", ".rbenv", ".pyenv",
    ".docker", ".colima", ".lima",
    ".ssh", ".gnupg", ".kube", ".aws",
    # IDE / editor
    ".vscode", ".idea", ".eclipse", ".vs",
    # Build artifacts
    "node_modules", "__pycache__", ".git", ".svn", ".hg",
    ".tox", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    "venv", ".venv", "env", ".env",
    "dist", "build", "target", "out", "bin", "obj",
    ".next", ".nuxt", ".turbo",
    # Large data
    ".gradle", ".m2", ".sbt",
    "Pods", "DerivedData",
    # macOS
    ".Spotlight-V100", ".fseventsd", ".TemporaryItems",
    "Photos Library.photoslibrary",
    "Music", "Movies",
}

# Files larger than this are skipped (10 MB)
_MAX_FILE_SIZE = int(getenv("VAULT_FILES_MAX_SIZE", str(10 * 1024 * 1024)))

# Default scan roots under $HOME
_DEFAULT_SCAN_DIRS = "Documents,Desktop,Downloads,Projects,Code,GitHub,Developer,repos,src,work,notes"


class FilesConnector(BaseConnector):
    """Scans home directory for useful documents and code, indexes into vector store."""

    source = "files"

    def __init__(self, store: PersonalStore, encoder: LocalVectorEncoder, cursor: dict | None = None):
        self._store = store
        self._encoder = encoder
        self._cursor = cursor or {}

    def sync(self, *, full: bool = False) -> SyncResult:
        """Scan configured directories and index new/modified files."""
        scan_roots = self._resolve_scan_roots()
        last_mtime = 0.0 if full else float(self._cursor.get("last_mtime", 0) or 0)

        documents = 0
        chunks = 0
        files_scanned = 0
        files_skipped = 0
        max_mtime = last_mtime

        for root in scan_roots:
            if not root.exists():
                continue
            for path in _walk_filtered(root):
                files_scanned += 1

                try:
                    stat = path.stat()
                except OSError:
                    files_skipped += 1
                    continue

                # Skip files not modified since last sync
                if stat.st_mtime <= last_mtime:
                    continue

                # Skip files too large
                if stat.st_size > _MAX_FILE_SIZE:
                    files_skipped += 1
                    continue

                text = _read_file_text(path)
                if not text.strip():
                    files_skipped += 1
                    continue

                # Truncate very long files to first 50k chars for embedding
                if len(text) > 50_000:
                    text = text[:50_000]

                checksum = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
                doc_id = f"files:{checksum[:32]}"

                try:
                    created_docs, created_chunks = ingest_document(
                        store=self._store,
                        encoder=self._encoder,
                        payload={
                            "doc_id": doc_id,
                            "source": self.source,
                            "external_id": str(path),
                            "thread_id": str(path.parent),
                            "account_id": "local",
                            "title": path.name,
                            "author": None,
                            "participants": [],
                            "timestamp_utc": datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                            "deep_link": f"file://{path}",
                            "metadata": {
                                "path": str(path),
                                "size": stat.st_size,
                                "suffix": path.suffix.lower(),
                                "category": "code" if path.suffix.lower() in _CODE_SUFFIXES else "document",
                            },
                            "checksum": checksum,
                        },
                        body_text=text,
                    )
                    documents += created_docs
                    chunks += created_chunks
                    max_mtime = max(max_mtime, stat.st_mtime)
                except Exception:
                    logger.warning("Failed to ingest %s", path, exc_info=True)
                    files_skipped += 1

        next_cursor = {
            **self._cursor,
            "last_mtime": max_mtime,
            "synced_at": datetime.now(UTC).isoformat(),
            "files_scanned": files_scanned,
            "files_skipped": files_skipped,
        }
        logger.info("files sync: scanned=%d indexed=%d chunks=%d skipped=%d", files_scanned, documents, chunks, files_skipped)
        return SyncResult(documents=documents, chunks=chunks, message="files sync completed", cursor=next_cursor)

    def _resolve_scan_roots(self) -> list[Path]:
        """Determine which directories to scan."""
        # Check for explicit allowlist first (backwards compatible)
        try:
            allowlist = self._store.list_file_allowlist()
            if allowlist:
                return [Path(p).expanduser() for p in allowlist]
        except Exception:
            pass

        # Fall back to configured scan dirs under $HOME
        home = Path.home()
        dir_names = getenv("VAULT_FILES_SCAN_DIRS", _DEFAULT_SCAN_DIRS).split(",")
        roots: list[Path] = []
        for name in dir_names:
            name = name.strip()
            if not name:
                continue
            candidate = home / name
            if candidate.exists() and candidate.is_dir():
                roots.append(candidate)
        return roots


def _walk_filtered(root: Path):
    """Walk directory tree, skipping excluded dirs and unsupported files."""
    try:
        entries = sorted(root.iterdir())
    except (PermissionError, OSError):
        return

    for entry in entries:
        if entry.name.startswith(".") and entry.name in _SKIP_DIRS:
            continue
        if entry.is_dir():
            if entry.name in _SKIP_DIRS:
                continue
            yield from _walk_filtered(entry)
        elif entry.is_file():
            if entry.suffix.lower() in _SUPPORTED_SUFFIXES or entry.name.lower() in {"makefile", "dockerfile", "readme", "license", "changelog"}:
                yield entry


def _read_file_text(path: Path) -> str:
    """Read text content from a file. Handles plain text and basic PDF extraction."""
    suffix = path.suffix.lower()
    try:
        if suffix == ".ipynb":
            return _read_notebook(path)
        if suffix == ".pdf":
            return _read_pdf(path)
        if suffix in {".doc", ".docx", ".xls", ".xlsx", ".pptx"}:
            # Office files need python-docx/openpyxl — skip if not installed
            return _read_office(path)
        return path.read_text(errors="ignore")
    except (OSError, UnicodeDecodeError):
        return ""


def _read_pdf(path: Path) -> str:
    """Best-effort PDF text extraction."""
    try:
        raw = path.read_bytes()
        # Simple text extraction from PDF stream objects
        text = raw.decode("latin-1", errors="ignore")
        return text
    except OSError:
        return ""


def _read_notebook(path: Path) -> str:
    """Extract code and markdown cells from Jupyter notebooks."""
    import json

    try:
        with open(path) as f:
            nb = json.load(f)
        cells = nb.get("cells", [])
        parts: list[str] = []
        for cell in cells:
            cell_type = cell.get("cell_type", "")
            source = "".join(cell.get("source", []))
            if cell_type == "markdown":
                parts.append(source)
            elif cell_type == "code":
                parts.append(f"```python\n{source}\n```")
        return "\n\n".join(parts)
    except (json.JSONDecodeError, OSError, KeyError):
        return ""


def _read_office(path: Path) -> str:
    """Best-effort Office file reading — returns empty if libs not installed."""
    suffix = path.suffix.lower()
    try:
        if suffix in {".doc", ".docx"}:
            import docx
            doc = docx.Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        if suffix in {".xls", ".xlsx"}:
            import openpyxl
            wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
            parts: list[str] = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    line = "\t".join(str(c) for c in row if c is not None)
                    if line.strip():
                        parts.append(line)
            wb.close()
            return "\n".join(parts)
    except (ImportError, Exception):
        return ""
    return ""
