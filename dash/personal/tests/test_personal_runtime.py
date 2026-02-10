"""Regression tests for personal runtime memory and citation behavior."""

import unittest

from dash.personal.contracts import PersonalAskRequest
from dash.personal.learning import PersonalReflectionEngine
from dash.personal.memory import MemoryManager
from dash.personal.orchestrator import PersonalOrchestrator
from dash.personal.retrieval import PersonalRetriever
from dash.personal.store import PersonalStore, PersonalStoreError


class PersonalRuntimeTests(unittest.TestCase):
    """Behavioral tests for memory lifecycle and ask safeguards."""

    def setUp(self) -> None:
        self.store = PersonalStore("sqlite+pysqlite:///:memory:")
        self.store.ensure_schema()
        self.memory = MemoryManager(self.store)
        self.orchestrator = PersonalOrchestrator(
            store=self.store,
            retriever=PersonalRetriever(self.store),
            memory_manager=self.memory,
            reflection_engine=PersonalReflectionEngine(),
        )

    def test_memory_activation_requires_evidence(self) -> None:
        candidate_id = self.store.create_memory_candidate(
            run_id="run-1",
            kind="ReasoningRule",
            scope="user-global",
            title="candidate without evidence",
            learning="Always answer quickly.",
            confidence=80,
            evidence_citation_ids=[],
            status="proposed",
            metadata_dict={},
        )

        with self.assertRaises(PersonalStoreError):
            self.memory.approve_candidate(candidate_id)

    def test_conflicting_memory_demotes_weaker(self) -> None:
        first_id = self.store.create_memory_item(
            kind="ReasoningRule",
            scope="user-global",
            statement="Do not speculate without citations.",
            confidence=60,
            source="seed",
            supersedes_id=None,
            metadata_dict={},
        )
        self.assertGreater(first_id, 0)

        candidate_id = self.store.create_memory_candidate(
            run_id="run-2",
            kind="ReasoningRule",
            scope="user-global",
            title="conflicting guidance",
            learning="Always speculate with citations when uncertain.",
            confidence=90,
            evidence_citation_ids=["c_x_1"],
            status="proposed",
            metadata_dict={},
        )
        item, demoted = self.memory.approve_candidate(candidate_id)

        self.assertEqual(item["activation_state"], "active")
        self.assertIn(first_id, demoted)
        demoted_item = self.store.get_memory_item(first_id)
        self.assertIsNotNone(demoted_item)
        assert demoted_item is not None
        self.assertEqual(demoted_item["activation_state"], "stale")

    def test_ask_returns_insufficient_evidence_without_chunks(self) -> None:
        response = self.orchestrator.run_ask(PersonalAskRequest(question="What happened yesterday?"))

        self.assertEqual(response.status, "success")
        self.assertTrue(response.answer)
        self.assertIn("Insufficient evidence", response.answer or "")
        self.assertEqual(response.citations, [])
        self.assertGreater(len(response.missing_evidence), 0)

    def test_ask_returns_citations_when_chunks_exist(self) -> None:
        self.store.upsert_document(
            {
                "doc_id": "files:test-doc",
                "source": "files",
                "external_id": "/tmp/test.txt",
                "title": "weekly notes",
                "body_text": "Lewis discussed launch metrics and email quality.",
                "author": "Utsav",
                "participants": ["Utsav"],
                "deep_link": "/tmp/test.txt",
                "metadata": {},
            },
            ["Lewis discussed launch metrics and email quality."],
        )

        response = self.orchestrator.run_ask(
            PersonalAskRequest(question="What did Lewis discuss about email quality?", include_debug=True)
        )

        self.assertEqual(response.status, "success")
        self.assertGreater(len(response.citations), 0)
        self.assertIn("Based only on the cited evidence", response.answer or "")


if __name__ == "__main__":
    unittest.main()
