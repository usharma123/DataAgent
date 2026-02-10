"""Base connector contract."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SyncResult:
    """Standardized connector sync result."""

    documents: int
    chunks: int
    message: str
    cursor: dict | None = None


class BaseConnector:
    """Connector base interface."""

    source: str

    def connect(self, cursor: dict | None = None) -> None:
        """Mark source as connected."""
        _ = cursor

    def sync(self, *, full: bool = False) -> SyncResult:
        """Run source sync."""
        _ = full
        raise NotImplementedError
