"""Gmail connector using REST API with local persistence."""

import base64
import hashlib
from datetime import UTC, datetime
from os import getenv

import httpx

from dash.personal.connectors.base import BaseConnector, SyncResult
from dash.personal.ingest import ingest_document
from dash.personal.store import PersonalStore, PersonalStoreError
from dash.personal.vector import LocalVectorEncoder


class GmailConnector(BaseConnector):
    """Incremental Gmail ingestion via read-only REST APIs."""

    source = "gmail"

    def __init__(self, store: PersonalStore, encoder: LocalVectorEncoder, cursor: dict | None):
        self._store = store
        self._encoder = encoder
        self._cursor = cursor or {}
        self._base_url = "https://gmail.googleapis.com/gmail/v1/users/me"

    def connect(self, cursor: dict | None = None) -> None:
        """Validate credentials and optionally persist OAuth refresh token."""
        supplied_refresh = (cursor or {}).get("refresh_token")
        if supplied_refresh:
            self._store.upsert_source(
                source=self.source,
                connected=True,
                cursor={**self._cursor, "refresh_token": str(supplied_refresh)},
            )
            self._cursor = {**self._cursor, "refresh_token": str(supplied_refresh)}

        token = self._access_token()
        _request_json("GET", f"{self._base_url}/profile", token=token)

    def sync(self, *, full: bool = False) -> SyncResult:
        """Sync Gmail messages and store local chunk embeddings."""
        token = self._access_token()
        last_internal_ts = 0 if full else int(self._cursor.get("last_internal_ts", 0) or 0)
        default_query = getenv("GMAIL_SYNC_QUERY", "newer_than:365d")
        query = default_query if last_internal_ts <= 0 else f"after:{last_internal_ts // 1000}"

        message_ids = self._list_message_ids(token=token, query=query)
        documents = 0
        chunks = 0
        max_internal_ts = last_internal_ts

        for message_id in message_ids:
            raw = _request_json("GET", f"{self._base_url}/messages/{message_id}", token=token, params={"format": "full"})
            internal_date_ms = int(raw.get("internalDate", 0) or 0)
            if internal_date_ms <= last_internal_ts:
                continue

            payload = raw.get("payload", {})
            headers = _header_map(payload.get("headers", []))
            subject = headers.get("subject")
            sender = headers.get("from")
            participants = [value for value in [headers.get("to"), headers.get("cc")] if value]
            body = _extract_body_text(payload)
            if not body:
                body = subject or "(empty message)"

            timestamp = datetime.fromtimestamp(internal_date_ms / 1000, tz=UTC)
            thread_id = str(raw.get("threadId") or message_id)
            checksum = hashlib.sha256(body.encode("utf-8", errors="ignore")).hexdigest()

            created_docs, created_chunks = ingest_document(
                store=self._store,
                encoder=self._encoder,
                payload={
                    "doc_id": f"gmail:{message_id}",
                    "source": self.source,
                    "external_id": message_id,
                    "thread_id": thread_id,
                    "account_id": headers.get("delivered-to") or "me",
                    "title": subject,
                    "author": sender,
                    "participants": participants,
                    "timestamp_utc": timestamp,
                    "deep_link": f"https://mail.google.com/mail/u/0/#inbox/{thread_id}",
                    "metadata": {
                        "label_ids": raw.get("labelIds", []),
                        "snippet": raw.get("snippet", ""),
                        "history_id": raw.get("historyId"),
                    },
                    "checksum": checksum,
                },
                body_text=body,
            )
            documents += created_docs
            chunks += created_chunks
            max_internal_ts = max(max_internal_ts, internal_date_ms)

        next_cursor = {
            **self._cursor,
            "last_internal_ts": max_internal_ts,
            "synced_at": datetime.now(UTC).isoformat(),
        }
        return SyncResult(documents=documents, chunks=chunks, message="gmail sync completed", cursor=next_cursor)

    def _list_message_ids(self, *, token: str, query: str) -> list[str]:
        message_ids: list[str] = []
        page_token: str | None = None
        max_pages = _read_positive_int("GMAIL_SYNC_MAX_PAGES", 3)

        for _ in range(max_pages):
            params = {"q": query, "maxResults": 100}
            if page_token:
                params["pageToken"] = page_token
            payload = _request_json("GET", f"{self._base_url}/messages", token=token, params=params)
            for item in payload.get("messages", []):
                message_id = item.get("id")
                if message_id:
                    message_ids.append(str(message_id))
            page_token = payload.get("nextPageToken")
            if not page_token:
                break

        return message_ids

    def _access_token(self) -> str:
        provided = getenv("GMAIL_ACCESS_TOKEN", "").strip()
        if provided:
            return provided

        refresh = getenv("GMAIL_REFRESH_TOKEN", "").strip() or str(self._cursor.get("refresh_token", "")).strip()
        client_id = getenv("GMAIL_CLIENT_ID", "").strip()
        client_secret = getenv("GMAIL_CLIENT_SECRET", "").strip()
        if not refresh or not client_id or not client_secret:
            raise PersonalStoreError(
                "Gmail credentials missing. Set GMAIL_ACCESS_TOKEN or GMAIL_CLIENT_ID/GMAIL_CLIENT_SECRET/GMAIL_REFRESH_TOKEN"
            )

        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        }
        response = httpx.post("https://oauth2.googleapis.com/token", data=payload, timeout=20.0)
        response.raise_for_status()
        token_payload = response.json()
        access_token = str(token_payload.get("access_token", "")).strip()
        if not access_token:
            raise PersonalStoreError("Failed to acquire Gmail access token from refresh token")
        return access_token


def _request_json(
    method: str,
    url: str,
    *,
    token: str,
    params: dict | None = None,
    body: dict | None = None,
) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=25.0) as client:
        response = client.request(method, url, headers=headers, params=params, json=body)
    response.raise_for_status()
    return response.json()


def _header_map(raw_headers: list[dict]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for item in raw_headers:
        name = str(item.get("name", "")).strip().lower()
        value = str(item.get("value", "")).strip()
        if name:
            mapped[name] = value
    return mapped


def _extract_body_text(payload: dict) -> str:
    body_data = payload.get("body", {}).get("data")
    if body_data:
        text = _decode_base64(body_data)
        if text:
            return text

    for part in payload.get("parts", []) or []:
        mime = str(part.get("mimeType", "")).lower()
        data = part.get("body", {}).get("data")
        if not data:
            nested = _extract_body_text(part)
            if nested:
                return nested
            continue
        text = _decode_base64(data)
        if mime == "text/plain" and text:
            return text
        if mime == "text/html" and text:
            return _strip_html(text)

    return ""


def _decode_base64(value: str) -> str:
    try:
        padded = value + "=" * (-len(value) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("utf-8"))
        return raw.decode("utf-8", errors="ignore")
    except (ValueError, OSError):
        return ""


def _strip_html(value: str) -> str:
    cleaned = value.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    return " ".join(_token for _token in cleaned.replace("<", " ").replace(">", " ").split())


def _read_positive_int(name: str, default: int) -> int:
    raw = getenv(name)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return parsed if parsed > 0 else default
