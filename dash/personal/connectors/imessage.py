"""iMessage connector using local Messages SQLite database."""

import hashlib
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from os import getenv
from pathlib import Path

from dash.personal.connectors.base import BaseConnector, SyncResult
from dash.personal.ingest import bulk_ingest
from dash.personal.store import PersonalStore, PersonalStoreError
from dash.personal.vector import LocalVectorEncoder

_APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)


class IMessageConnector(BaseConnector):
    """Incremental iMessage ingestion from macOS chat.db."""

    source = "imessage"

    def __init__(self, store: PersonalStore, encoder: LocalVectorEncoder, cursor: dict | None):
        self._store = store
        self._encoder = encoder
        self._cursor = cursor or {}

    def sync(self, *, full: bool = False) -> SyncResult:
        """Read new iMessage rows and index text + attachment metadata."""
        db_path = Path(getenv("IMESSAGE_DB_PATH", "~/Library/Messages/chat.db")).expanduser()
        if not db_path.exists():
            raise PersonalStoreError(f"iMessage database not found at {db_path}")

        last_rowid = 0 if full else int(self._cursor.get("last_rowid", 0) or 0)
        limit = _read_positive_int("IMESSAGE_SYNC_LIMIT", 300)
        batch_size = _read_positive_int("IMESSAGE_BATCH_SIZE", 500)

        documents = 0
        chunks = 0
        max_rowid = last_rowid

        with _open_readonly_sqlite(db_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    m.ROWID AS rowid,
                    m.guid,
                    m.text,
                    m.subject,
                    m.attributedBody,
                    m.date,
                    m.is_from_me,
                    m.service,
                    h.id AS handle_id,
                    c.chat_identifier,
                    c.display_name
                FROM message m
                LEFT JOIN handle h ON h.ROWID = m.handle_id
                LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
                LEFT JOIN chat c ON c.ROWID = cmj.chat_id
                WHERE m.ROWID > ?
                ORDER BY m.ROWID ASC
                LIMIT ?
                """,
                (last_rowid, limit),
            ).fetchall()

            batch: list[tuple[dict, str]] = []
            for row in rows:
                rowid = int(row[0])
                guid = str(row[1] or f"msg-{rowid}")
                text = str(row[2] or "").strip()
                subject = str(row[3] or "").strip()
                attributed = row[4]
                raw_date = row[5]
                is_from_me = int(row[6] or 0)
                service = str(row[7] or "iMessage")
                handle_id = str(row[8] or "unknown")
                chat_identifier = str(row[9] or "")
                display_name = str(row[10] or "")

                attachments = _attachment_metadata(conn, rowid)
                body = text or subject or _decode_attributed(attributed)
                if not body and attachments:
                    body = "Attachment-only message"
                if not body:
                    continue

                timestamp = _apple_time_to_datetime(raw_date)
                checksum = hashlib.sha256(body.encode("utf-8", errors="ignore")).hexdigest()

                payload = {
                    "doc_id": f"imessage:{rowid}",
                    "source": self.source,
                    "external_id": guid,
                    "thread_id": chat_identifier or None,
                    "account_id": service,
                    "title": display_name or chat_identifier or "iMessage",
                    "author": "me" if is_from_me else handle_id,
                    "participants": [handle_id] if handle_id else [],
                    "timestamp_utc": timestamp,
                    "deep_link": f"imessage://message/{guid}",
                    "metadata": {
                        "guid": guid,
                        "is_from_me": bool(is_from_me),
                        "service": service,
                        "attachments": attachments,
                    },
                    "checksum": checksum,
                }
                batch.append((payload, body))
                max_rowid = max(max_rowid, rowid)

                if len(batch) >= batch_size:
                    created_docs, created_chunks = bulk_ingest(
                        store=self._store, encoder=self._encoder, items=batch,
                    )
                    documents += created_docs
                    chunks += created_chunks
                    batch = []

            if batch:
                created_docs, created_chunks = bulk_ingest(
                    store=self._store, encoder=self._encoder, items=batch,
                )
                documents += created_docs
                chunks += created_chunks

        next_cursor = {**self._cursor, "last_rowid": max_rowid, "synced_at": datetime.now(UTC).isoformat()}
        return SyncResult(documents=documents, chunks=chunks, message="imessage sync completed", cursor=next_cursor)


def _open_readonly_sqlite(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _attachment_metadata(conn: sqlite3.Connection, rowid: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT a.filename, a.mime_type, a.transfer_name, a.total_bytes
        FROM message_attachment_join maj
        JOIN attachment a ON a.ROWID = maj.attachment_id
        WHERE maj.message_id = ?
        """,
        (rowid,),
    ).fetchall()
    attachments: list[dict] = []
    for row in rows:
        attachments.append(
            {
                "filename": str(row[0] or ""),
                "mime_type": str(row[1] or ""),
                "transfer_name": str(row[2] or ""),
                "total_bytes": int(row[3] or 0),
            }
        )
    return attachments


def _apple_time_to_datetime(value: object) -> datetime:
    if value is None:
        return datetime.now(UTC)
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return datetime.now(UTC)

    # Modern macOS stores message.date in nanoseconds since 2001-01-01.
    if abs(raw) > 10_000_000_000:
        return _APPLE_EPOCH + timedelta(seconds=raw / 1_000_000_000)
    return _APPLE_EPOCH + timedelta(seconds=raw)


def _decode_attributed(blob: object) -> str:
    """Extract plain text from NSAttributedString binary blob.

    The blob is a macOS typedstream containing the message text between
    a ``\\x01+<len>`` marker and a ``\\x86`` terminator.
    """
    if blob is None:
        return ""
    if isinstance(blob, str):
        return blob.strip()
    if not isinstance(blob, (bytes, bytearray)):
        return ""
    raw = bytes(blob)
    match = re.search(rb"\x01\+.(.*?)\x86", raw, re.DOTALL)
    if match:
        text = match.group(1).decode("utf-8", errors="replace").strip()
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffd]", "", text)
        if text:
            return text
    # Fallback: naive decode (strips binary noise)
    text = raw.decode("utf-8", errors="ignore")
    return " ".join(text.split())


def _read_positive_int(name: str, default: int) -> int:
    raw = getenv(name)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return parsed if parsed > 0 else default
