"""Source connection and sync orchestration for personal runtime."""

from datetime import UTC, datetime

from dash.personal.connectors import FilesConnector, GmailConnector, IMessageConnector, SlackConnector
from dash.personal.connectors.base import BaseConnector
from dash.personal.store import PersonalStore, PersonalStoreError
from dash.personal.vector import LocalVectorEncoder


class PersonalSyncService:
    """Coordinates source-specific connectors and persists cursor state."""

    def __init__(self, store: PersonalStore):
        self._store = store
        self._encoder = LocalVectorEncoder()

    def connect_source(self, *, source: str, cursor: dict | None = None) -> None:
        """Connect source with optional connector-specific payload."""
        connector = self._connector_for(source)
        connector.connect(cursor=cursor)
        merged_cursor = {**(self._source_cursor(source) or {}), **(cursor or {})}
        self._store.upsert_source(source=source, connected=True, cursor=merged_cursor)

    def sync_source(self, *, source: str, full: bool = False) -> tuple[int, int, str]:
        """Run source sync and update source cursor state."""
        connector = self._connector_for(source)
        result = connector.sync(full=full)

        merged_cursor = {
            **(self._source_cursor(source) or {}),
            **(result.cursor or {}),
            "synced_at": datetime.now(UTC).isoformat(),
        }
        self._store.update_source_sync(source=source, cursor=merged_cursor)
        return result.documents, result.chunks, result.message

    def _connector_for(self, source: str) -> BaseConnector:
        cursor = self._source_cursor(source)
        if source == "files":
            return FilesConnector(store=self._store, encoder=self._encoder, cursor=cursor)
        if source == "gmail":
            return GmailConnector(store=self._store, encoder=self._encoder, cursor=cursor)
        if source == "slack":
            return SlackConnector(store=self._store, encoder=self._encoder, cursor=cursor)
        if source == "imessage":
            return IMessageConnector(store=self._store, encoder=self._encoder, cursor=cursor)
        raise PersonalStoreError(f"Unsupported source: {source}")

    def _source_cursor(self, source: str) -> dict:
        row = self._store.get_source(source)
        if row is None:
            return {}
        cursor = row.get("cursor")
        if isinstance(cursor, dict):
            return cursor
        return {}
