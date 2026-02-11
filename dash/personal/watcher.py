"""File system watcher — auto-indexes new/modified files using macOS FSEvents."""

import logging
import threading
import time
from os import getenv
from pathlib import Path

from dash.personal.connectors.files import _SKIP_DIRS, _SUPPORTED_SUFFIXES
from dash.personal.store import PersonalStore
from dash.personal.vector import LocalVectorEncoder

logger = logging.getLogger(__name__)

# How long to wait after a file change before indexing (seconds).
# Groups rapid edits (e.g. save-save-save) into one indexing pass.
_DEBOUNCE_SECONDS = float(getenv("VAULT_WATCHER_DEBOUNCE", "5"))

# Default scan roots (same as FilesConnector)
_DEFAULT_SCAN_DIRS = "Documents,Desktop,Downloads,Projects,Code,GitHub,Developer,repos,src,work,notes"


class FileWatcher:
    """Watches configured directories for file changes and auto-indexes them.

    Uses the `watchdog` library which leverages macOS FSEvents for efficient
    native file system monitoring with minimal CPU overhead.
    """

    def __init__(self, store: PersonalStore, encoder: LocalVectorEncoder | None = None):
        self._store = store
        self._encoder = encoder or LocalVectorEncoder()
        self._pending: dict[str, float] = {}  # path -> timestamp of last change
        self._lock = threading.Lock()
        self._observer = None
        self._running = False
        self._debounce_thread: threading.Thread | None = None

    def start(self) -> None:
        """Start watching configured directories."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler, FileSystemEvent
        except ImportError:
            logger.error("watchdog not installed — file watcher disabled. Run: pip install watchdog")
            return

        watch_roots = self._resolve_watch_roots()
        if not watch_roots:
            logger.warning("No directories to watch — file watcher not started")
            return

        watcher = self

        class _Handler(FileSystemEventHandler):
            def on_created(self, event: FileSystemEvent) -> None:
                if not event.is_directory:
                    watcher._on_file_changed(event.src_path)

            def on_modified(self, event: FileSystemEvent) -> None:
                if not event.is_directory:
                    watcher._on_file_changed(event.src_path)

            def on_moved(self, event: FileSystemEvent) -> None:
                if not event.is_directory and hasattr(event, "dest_path"):
                    watcher._on_file_changed(event.dest_path)

        handler = _Handler()
        self._observer = Observer()

        for root in watch_roots:
            logger.info("Watching %s for file changes", root)
            self._observer.schedule(handler, str(root), recursive=True)

        self._running = True
        self._observer.start()

        # Start debounce processor thread
        self._debounce_thread = threading.Thread(target=self._debounce_loop, daemon=True, name="file-watcher-debounce")
        self._debounce_thread.start()

        logger.info("File watcher started — monitoring %d directories", len(watch_roots))

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        logger.info("File watcher stopped")

    def _on_file_changed(self, path_str: str) -> None:
        """Called by watchdog when a file is created/modified/moved."""
        path = Path(path_str)

        # Quick filters — skip irrelevant files immediately
        if not path.is_file():
            return
        if path.suffix.lower() not in _SUPPORTED_SUFFIXES and path.name.lower() not in {"makefile", "dockerfile", "readme", "license", "changelog"}:
            return
        if any(part in _SKIP_DIRS for part in path.parts):
            return

        with self._lock:
            self._pending[path_str] = time.monotonic()

    def _debounce_loop(self) -> None:
        """Background thread that waits for changes to settle, then indexes."""
        while self._running:
            time.sleep(1)

            ready: list[str] = []
            now = time.monotonic()

            with self._lock:
                for path_str, changed_at in list(self._pending.items()):
                    if now - changed_at >= _DEBOUNCE_SECONDS:
                        ready.append(path_str)
                for path_str in ready:
                    del self._pending[path_str]

            if ready:
                self._index_files(ready)

    def _index_files(self, paths: list[str]) -> None:
        """Index a batch of changed files."""
        from dash.personal.connectors.files import _read_file_text, _CODE_SUFFIXES, _MAX_FILE_SIZE
        from dash.personal.ingest import ingest_document

        import hashlib
        from datetime import UTC, datetime

        indexed = 0
        for path_str in paths:
            path = Path(path_str)
            try:
                if not path.exists() or not path.is_file():
                    continue

                stat = path.stat()
                if stat.st_size > _MAX_FILE_SIZE:
                    continue

                text = _read_file_text(path)
                if not text.strip():
                    continue

                if len(text) > 50_000:
                    text = text[:50_000]

                checksum = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
                doc_id = f"files:{checksum[:32]}"

                ingest_document(
                    store=self._store,
                    encoder=self._encoder,
                    payload={
                        "doc_id": doc_id,
                        "source": "files",
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
                            "auto_indexed": True,
                        },
                        "checksum": checksum,
                    },
                    body_text=text,
                )
                indexed += 1
            except Exception:
                logger.warning("Watcher failed to index %s", path_str, exc_info=True)

        if indexed:
            logger.info("Auto-indexed %d/%d changed files", indexed, len(paths))

    def _resolve_watch_roots(self) -> list[Path]:
        """Determine which directories to watch."""
        # Check for explicit allowlist first
        try:
            allowlist = self._store.list_file_allowlist()
            if allowlist:
                return [Path(p).expanduser() for p in allowlist if Path(p).expanduser().is_dir()]
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


# ── Singleton for app lifecycle ────────────────────────────────────────────────

_watcher: FileWatcher | None = None


def start_file_watcher(store: PersonalStore) -> FileWatcher:
    """Start the global file watcher singleton."""
    global _watcher
    if _watcher is not None:
        return _watcher
    _watcher = FileWatcher(store=store)
    _watcher.start()
    return _watcher


def stop_file_watcher() -> None:
    """Stop the global file watcher."""
    global _watcher
    if _watcher is not None:
        _watcher.stop()
        _watcher = None
