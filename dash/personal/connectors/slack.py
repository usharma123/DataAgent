"""Slack connector using user token history APIs."""

import hashlib
from datetime import UTC, datetime
from os import getenv

import httpx

from dash.personal.connectors.base import BaseConnector, SyncResult
from dash.personal.ingest import ingest_document
from dash.personal.store import PersonalStore, PersonalStoreError
from dash.personal.vector import LocalVectorEncoder


class SlackConnector(BaseConnector):
    """Incremental Slack ingestion for configured conversations."""

    source = "slack"

    def __init__(self, store: PersonalStore, encoder: LocalVectorEncoder, cursor: dict | None):
        self._store = store
        self._encoder = encoder
        self._cursor = cursor or {}
        self._api_base = "https://slack.com/api"

    def connect(self, cursor: dict | None = None) -> None:
        """Validate Slack token and optionally save from connect payload."""
        supplied = (cursor or {}).get("token")
        if supplied:
            self._cursor = {**self._cursor, "token": str(supplied)}
            self._store.upsert_source(source=self.source, connected=True, cursor=self._cursor)

        token = self._token()
        payload = self._request("auth.test", token=token)
        if not payload.get("ok"):
            raise PersonalStoreError(f"Slack auth failed: {payload.get('error', 'unknown error')}")

    def sync(self, *, full: bool = False) -> SyncResult:
        """Sync Slack messages for configured or discovered conversations."""
        token = self._token()
        channel_cursors = dict(self._cursor.get("channel_cursors", {}))
        conversations = _configured_conversations() or self._discover_conversations(token)

        documents = 0
        chunks = 0
        for channel_id in conversations:
            oldest = "0" if full else str(channel_cursors.get(channel_id, "0"))
            history = self._request(
                "conversations.history",
                token=token,
                params={"channel": channel_id, "limit": 200, "oldest": oldest, "inclusive": False},
            )
            if not history.get("ok"):
                continue

            latest_ts = float(oldest) if oldest else 0.0
            for message in history.get("messages", []):
                ts = str(message.get("ts", "")).strip()
                text = str(message.get("text", "")).strip()
                if not ts or not text:
                    continue

                ts_float = _parse_ts(ts)
                if ts_float <= latest_ts:
                    continue
                latest_ts = max(latest_ts, ts_float)

                timestamp = datetime.fromtimestamp(ts_float, tz=UTC)
                user = str(message.get("user") or message.get("username") or "unknown")
                thread_ts = str(message.get("thread_ts") or ts)
                checksum = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
                deep_link = self._message_permalink(token=token, channel=channel_id, ts=ts)

                created_docs, created_chunks = ingest_document(
                    store=self._store,
                    encoder=self._encoder,
                    payload={
                        "doc_id": f"slack:{channel_id}:{ts}",
                        "source": self.source,
                        "external_id": ts,
                        "thread_id": thread_ts,
                        "account_id": channel_id,
                        "title": f"Slack message in {channel_id}",
                        "author": user,
                        "participants": [user],
                        "timestamp_utc": timestamp,
                        "deep_link": deep_link,
                        "metadata": {
                            "channel": channel_id,
                            "subtype": message.get("subtype"),
                            "reply_count": message.get("reply_count", 0),
                        },
                        "checksum": checksum,
                    },
                    body_text=text,
                )
                documents += created_docs
                chunks += created_chunks

            channel_cursors[channel_id] = f"{latest_ts:.6f}"

        next_cursor = {
            **self._cursor,
            "channel_cursors": channel_cursors,
            "synced_at": datetime.now(UTC).isoformat(),
        }
        return SyncResult(documents=documents, chunks=chunks, message="slack sync completed", cursor=next_cursor)

    def _discover_conversations(self, token: str) -> list[str]:
        payload = self._request(
            "users.conversations",
            token=token,
            params={"types": "public_channel,private_channel,im,mpim", "limit": 200},
        )
        if not payload.get("ok"):
            return []
        conversations: list[str] = []
        for item in payload.get("channels", []):
            cid = item.get("id")
            if cid:
                conversations.append(str(cid))
        return conversations

    def _message_permalink(self, *, token: str, channel: str, ts: str) -> str | None:
        payload = self._request("chat.getPermalink", token=token, params={"channel": channel, "message_ts": ts})
        if not payload.get("ok"):
            return None
        permalink = payload.get("permalink")
        return str(permalink) if permalink else None

    def _request(self, endpoint: str, *, token: str, params: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {token}"}
        with httpx.Client(timeout=20.0) as client:
            response = client.get(f"{self._api_base}/{endpoint}", headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    def _token(self) -> str:
        token = getenv("SLACK_USER_TOKEN", "").strip() or str(self._cursor.get("token", "")).strip()
        if not token:
            raise PersonalStoreError("Slack token missing. Set SLACK_USER_TOKEN or pass token in connect payload")
        return token


def _configured_conversations() -> list[str]:
    raw = getenv("SLACK_CONVERSATIONS", "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _parse_ts(ts: str) -> float:
    try:
        return float(ts)
    except ValueError:
        return 0.0
