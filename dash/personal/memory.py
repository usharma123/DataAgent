"""Memory management for personal agent runtime."""

import re
from dataclasses import dataclass

from dash.personal.retrieval import tokenize
from dash.personal.store import PersonalStore, PersonalStoreError

_NEGATION_RE = re.compile(r"\b(no|not|never|without|avoid)\b", flags=re.IGNORECASE)


@dataclass(frozen=True)
class MemorySelection:
    """Memory retrieval result for one ask run."""

    used: list[dict]
    skipped: list[dict]


class MemoryManager:
    """Handles memory candidate lifecycle and retrieval."""

    def __init__(self, store: PersonalStore):
        self._store = store

    def select_for_question(
        self,
        *,
        question: str,
        session_id: str | None,
        source_filters: list[str],
        top_k: int = 4,
    ) -> MemorySelection:
        """Select relevant memories for question and mark skipped low-relevance items."""
        _ = session_id  # reserved for future per-session scoping.
        items = self._store.list_memory_items(active_only=True)
        q_tokens = tokenize(question)

        scored: list[tuple[float, dict]] = []
        skipped: list[dict] = []
        for item in items:
            if int(item.get("confidence", 0)) < 60:
                skipped.append(item)
                continue
            if item["scope"] == "source-specific" and source_filters:
                mem_source = str(item.get("metadata", {}).get("source", "")).strip().lower()
                if mem_source and mem_source not in source_filters:
                    skipped.append(item)
                    continue

            item_tokens = tokenize(str(item["statement"]))
            overlap = len(q_tokens & item_tokens)
            if overlap == 0:
                skipped.append(item)
                continue
            score = overlap / max(1, len(q_tokens))
            if score < 0.15:
                skipped.append(item)
                continue
            scored.append((score, item))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        used = [item for _, item in scored[:top_k]]
        if len(used) < len(scored):
            skipped.extend(item for _, item in scored[top_k:])
        return MemorySelection(used=used, skipped=skipped)

    def approve_candidate(self, candidate_id: int) -> tuple[dict, list[int]]:
        """Approve candidate, activate memory item, and stale conflicting items."""
        candidate = self._store.get_memory_candidate(candidate_id)
        if candidate is None:
            raise PersonalStoreError(f"Memory candidate {candidate_id} not found")

        evidence_ids = candidate.get("evidence_citation_ids", [])
        if not evidence_ids:
            raise PersonalStoreError("Memory candidate requires evidence citations before activation")

        self._store.mark_memory_candidate(candidate_id=candidate_id, status="approved")
        statement = str(candidate["learning"]).strip()
        item_id = self._store.create_memory_item(
            kind=candidate["kind"],
            scope=candidate["scope"],
            statement=statement,
            confidence=int(candidate["confidence"]),
            source="candidate_approval",
            supersedes_id=None,
            metadata_dict={
                "candidate_id": str(candidate_id),
                "title": candidate["title"],
                "evidence_citation_ids": evidence_ids,
            },
            activation_state="active",
        )
        self._store.create_memory_event(
            event="approved",
            reason="candidate approved by user",
            memory_item_id=item_id,
            memory_candidate_id=candidate_id,
        )

        demoted = self._demote_conflicts(new_item_id=item_id)
        item = self._store.get_memory_item(item_id)
        if item is None:
            raise PersonalStoreError(f"Failed to load approved memory item {item_id}")
        return item, demoted

    def reject_candidate(self, candidate_id: int) -> None:
        """Reject proposed candidate."""
        candidate = self._store.get_memory_candidate(candidate_id)
        if candidate is None:
            raise PersonalStoreError(f"Memory candidate {candidate_id} not found")
        self._store.mark_memory_candidate(candidate_id=candidate_id, status="rejected")
        self._store.create_memory_event(
            event="rejected",
            reason="candidate rejected by user",
            memory_candidate_id=candidate_id,
        )

    def deprecate_item(self, item_id: int) -> None:
        """Deprecate active memory item."""
        item = self._store.get_memory_item(item_id)
        if item is None:
            raise PersonalStoreError(f"Memory item {item_id} not found")
        self._store.update_memory_item(item_id=item_id, activation_state="deprecated")
        self._store.create_memory_event(
            event="deprecated",
            reason="memory manually deprecated",
            memory_item_id=item_id,
        )

    def _demote_conflicts(self, *, new_item_id: int) -> list[int]:
        new_item = self._store.get_memory_item(new_item_id)
        if new_item is None:
            return []

        active = [item for item in self._store.list_memory_items(active_only=True) if item["id"] != new_item_id]
        demoted: list[int] = []
        for item in active:
            if item["kind"] != new_item["kind"]:
                continue
            if item["scope"] != new_item["scope"]:
                continue
            if not _is_conflicting(str(new_item["statement"]), str(item["statement"])):
                continue

            lower_conf_item_id = item["id"] if int(item["confidence"]) <= int(new_item["confidence"]) else new_item_id
            if lower_conf_item_id == new_item_id:
                self._store.update_memory_item(item_id=new_item_id, activation_state="stale", supersedes_id=item["id"])
                self._store.create_memory_event(
                    event="auto_stale",
                    reason=f"conflicts with stronger memory {item['id']}",
                    memory_item_id=new_item_id,
                )
                demoted.append(new_item_id)
                return demoted

            self._store.update_memory_item(item_id=lower_conf_item_id, activation_state="stale", supersedes_id=new_item_id)
            self._store.create_memory_event(
                event="auto_stale",
                reason=f"conflicts with stronger memory {new_item_id}",
                memory_item_id=lower_conf_item_id,
            )
            demoted.append(lower_conf_item_id)

        return demoted


def _is_conflicting(a: str, b: str) -> bool:
    """Heuristic contradiction detector for short guidance statements."""
    a_tokens = tokenize(a)
    b_tokens = tokenize(b)
    if not a_tokens or not b_tokens:
        return False

    overlap = len(a_tokens & b_tokens) / max(1, min(len(a_tokens), len(b_tokens)))
    if overlap < 0.5:
        return False

    a_neg = bool(_NEGATION_RE.search(a))
    b_neg = bool(_NEGATION_RE.search(b))
    return a_neg != b_neg
