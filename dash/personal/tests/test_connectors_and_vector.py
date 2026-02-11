"""Tests for connectors and local vector retrieval."""

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from dash.personal.learning import PersonalReflectionEngine
from dash.personal.retrieval import PersonalRetriever
from dash.personal.store import PersonalStore
from dash.personal.sync import PersonalSyncService
from dash.personal.vector import LocalVectorEncoder


class ConnectorsAndVectorTests(unittest.TestCase):
    """Connector + vector DB behavior."""

    def setUp(self) -> None:
        self.store = PersonalStore("sqlite+pysqlite:///:memory:")
        self.store.ensure_schema()

    def test_imessage_sync_ingests_text_and_attachment_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "chat.db"
            self._seed_imessage_fixture(db_path)

            original = os.environ.get("IMESSAGE_DB_PATH")
            os.environ["IMESSAGE_DB_PATH"] = str(db_path)
            try:
                sync = PersonalSyncService(self.store)
                docs, chunks, message = sync.sync_source(source="imessage", full=True)
            finally:
                if original is None:
                    os.environ.pop("IMESSAGE_DB_PATH", None)
                else:
                    os.environ["IMESSAGE_DB_PATH"] = original

        self.assertIn("imessage sync completed", message)
        self.assertGreaterEqual(docs, 1)
        self.assertGreaterEqual(chunks, 1)

        rows = self.store.list_chunks(source_filters=["imessage"], time_from=None, time_to=None, limit=10)
        self.assertGreaterEqual(len(rows), 1)
        self.assertIsNotNone(rows[0].get("embedding_json"))

    def test_local_vector_embeddings_present_for_documents(self) -> None:
        encoder = LocalVectorEncoder()
        docs, chunks = self.store.upsert_document(
            {
                "doc_id": "files:1",
                "source": "files",
                "external_id": "/tmp/a.txt",
                "title": "note",
                "body_text": "launch quality metrics improved",
                "metadata": {},
            },
            ["launch quality metrics improved"],
            [encoder.encode("launch quality metrics improved")],
        )
        self.assertEqual(docs, 1)
        self.assertEqual(chunks, 1)

        retriever = PersonalRetriever(self.store)
        results = retriever.retrieve(
            question="quality metrics",
            source_filters=["files"],
            time_from=None,
            time_to=None,
            top_k=5,
        )
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].source, "files")

    def test_retrieval_handles_typo_via_char_ngrams(self) -> None:
        encoder = LocalVectorEncoder()
        self.store.upsert_document(
            {
                "doc_id": "files:typo",
                "source": "files",
                "external_id": "/tmp/typo.txt",
                "title": "weekly metrics",
                "body_text": "launch quality metrics improved after rollout",
                "metadata": {},
            },
            ["launch quality metrics improved after rollout"],
            [encoder.encode("launch quality metrics improved after rollout")],
        )

        retriever = PersonalRetriever(self.store)
        results = retriever.retrieve(
            question="quality metrcs rollout",
            source_filters=["files"],
            time_from=None,
            time_to=None,
            top_k=5,
        )

        self.assertGreaterEqual(len(results), 1)
        self.assertIn("metrics improved", results[0].text)

    def test_feedback_generates_source_specific_memory_templates(self) -> None:
        reflection = PersonalReflectionEngine()
        drafts = reflection.from_feedback(
            verdict="incorrect",
            comment="Need Slack context",
            corrected_answer="Use Slack DM context",
            corrected_filters=["slack"],
            corrected_source_scope="slack:dms",
            evidence_citation_ids=["c_run_1"],
        )
        self.assertGreaterEqual(len(drafts), 2)
        self.assertTrue(any(d.kind == "SourceQuirk" and d.scope == "source-specific" for d in drafts))

    def _seed_imessage_fixture(self, db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE message (
                    ROWID INTEGER PRIMARY KEY,
                    guid TEXT,
                    text TEXT,
                    subject TEXT,
                    attributedBody BLOB,
                    date INTEGER,
                    is_from_me INTEGER,
                    service TEXT,
                    handle_id INTEGER
                );
                CREATE TABLE handle (
                    ROWID INTEGER PRIMARY KEY,
                    id TEXT
                );
                CREATE TABLE chat (
                    ROWID INTEGER PRIMARY KEY,
                    chat_identifier TEXT,
                    display_name TEXT
                );
                CREATE TABLE chat_message_join (
                    chat_id INTEGER,
                    message_id INTEGER
                );
                CREATE TABLE attachment (
                    ROWID INTEGER PRIMARY KEY,
                    filename TEXT,
                    mime_type TEXT,
                    transfer_name TEXT,
                    total_bytes INTEGER
                );
                CREATE TABLE message_attachment_join (
                    message_id INTEGER,
                    attachment_id INTEGER
                );
                """
            )
            conn.execute("INSERT INTO handle (ROWID, id) VALUES (1, '+14155550123')")
            conn.execute("INSERT INTO chat (ROWID, chat_identifier, display_name) VALUES (1, 'chat123', 'Family')")
            conn.execute(
                "INSERT INTO message (ROWID, guid, text, subject, attributedBody, date, is_from_me, service, handle_id) "
                "VALUES (10, 'msg-guid-1', 'Dinner at 7?', NULL, NULL, 7000000000, 0, 'iMessage', 1)"
            )
            conn.execute("INSERT INTO chat_message_join (chat_id, message_id) VALUES (1, 10)")
            conn.execute(
                "INSERT INTO attachment (ROWID, filename, mime_type, transfer_name, total_bytes) "
                "VALUES (1, '/tmp/photo.jpg', 'image/jpeg', 'photo.jpg', 1234)"
            )
            conn.execute("INSERT INTO message_attachment_join (message_id, attachment_id) VALUES (10, 1)")
            conn.commit()
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
