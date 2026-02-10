"""Local knowledge retrieval for the native pipeline."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from dash.paths import BUSINESS_DIR, QUERIES_DIR, TABLES_DIR

_TOKEN_RE = re.compile(r"[a-z0-9_]+")
_QUERY_PATTERN_RE = re.compile(
    r"<query name>(.*?)</query name>.*?<query description>(.*?)</query description>.*?<query>(.*?)</query>",
    flags=re.IGNORECASE | re.DOTALL,
)
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "how",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "vs",
    "what",
    "which",
    "who",
    "with",
}


@dataclass(frozen=True)
class ContextChunk:
    """One retrievable chunk of local knowledge."""

    kind: str
    key: str
    title: str
    text: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievedContext:
    """A chunk plus lexical relevance score."""

    chunk: ContextChunk
    score: int


def tokenize(text: str) -> set[str]:
    """Normalize text into searchable tokens."""
    tokens = {t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1}
    return {t for t in tokens if t not in _STOP_WORDS}


def _strip_sql_comment_prefix(block: str) -> str:
    lines = [line.strip() for line in block.splitlines()]
    cleaned = [line[2:].lstrip() if line.startswith("--") else line for line in lines]
    return "\n".join(line for line in cleaned if line)


def parse_query_patterns(sql_text: str) -> list[ContextChunk]:
    """Parse tagged query patterns from a knowledge SQL file."""
    chunks: list[ContextChunk] = []
    for match in _QUERY_PATTERN_RE.finditer(sql_text):
        name = match.group(1).strip()
        description = _strip_sql_comment_prefix(match.group(2))
        query_sql = _strip_sql_comment_prefix(match.group(3)).strip()
        if not name or not query_sql:
            continue
        chunks.append(
            ContextChunk(
                kind="query_pattern",
                key=f"query:{name}",
                title=name,
                text=f"{description}\n{query_sql}".strip(),
                metadata={
                    "query_name": name,
                    "description": description,
                    "sql": query_sql,
                },
            )
        )
    return chunks


class LocalKnowledgeRetriever:
    """Loads local knowledge files and ranks chunks by token overlap."""

    def __init__(
        self,
        tables_dir: Path = TABLES_DIR,
        business_dir: Path = BUSINESS_DIR,
        queries_dir: Path = QUERIES_DIR,
    ):
        self._chunks = self._load_chunks(tables_dir, business_dir, queries_dir)

    def retrieve(self, question: str, top_k: int = 6) -> list[RetrievedContext]:
        """Return top context chunks relevant to the question."""
        question_tokens = tokenize(question)
        scored: list[RetrievedContext] = []
        for chunk in self._chunks:
            chunk_tokens = tokenize(f"{chunk.title}\n{chunk.text}")
            score = len(question_tokens & chunk_tokens)
            if score > 0:
                scored.append(RetrievedContext(chunk=chunk, score=score))
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:top_k]

    def _load_chunks(self, tables_dir: Path, business_dir: Path, queries_dir: Path) -> list[ContextChunk]:
        chunks: list[ContextChunk] = []
        chunks.extend(self._load_table_chunks(tables_dir))
        chunks.extend(self._load_business_chunks(business_dir))
        chunks.extend(self._load_query_chunks(queries_dir))
        return chunks

    def _load_table_chunks(self, tables_dir: Path) -> list[ContextChunk]:
        chunks: list[ContextChunk] = []
        if not tables_dir.exists():
            return chunks
        for path in sorted(tables_dir.glob("*.json")):
            try:
                with open(path) as handle:
                    data = json.load(handle)
            except (json.JSONDecodeError, OSError):
                continue
            table_name = data.get("table_name") or path.stem
            description = data.get("table_description", "")
            use_cases = ", ".join(data.get("use_cases", []))
            notes = "\n".join(data.get("data_quality_notes", []))
            text = "\n".join(part for part in [description, use_cases, notes] if part)
            chunks.append(
                ContextChunk(
                    kind="table",
                    key=f"table:{table_name}",
                    title=table_name,
                    text=text,
                )
            )
        return chunks

    def _load_business_chunks(self, business_dir: Path) -> list[ContextChunk]:
        chunks: list[ContextChunk] = []
        if not business_dir.exists():
            return chunks
        for path in sorted(business_dir.glob("*.json")):
            try:
                with open(path) as handle:
                    data = json.load(handle)
            except (json.JSONDecodeError, OSError):
                continue
            lines: list[str] = []
            for metric in data.get("metrics", []):
                name = metric.get("name", "")
                definition = metric.get("definition", "")
                lines.append(f"{name}: {definition}".strip(": "))
            for rule in data.get("business_rules", []):
                lines.append(str(rule))
            for gotcha in data.get("common_gotchas", []):
                issue = gotcha.get("issue", "")
                solution = gotcha.get("solution", "")
                lines.append(f"{issue}: {solution}".strip(": "))
            if lines:
                chunks.append(
                    ContextChunk(
                        kind="business",
                        key=f"business:{path.stem}",
                        title=path.stem,
                        text="\n".join(lines),
                    )
                )
        return chunks

    def _load_query_chunks(self, queries_dir: Path) -> list[ContextChunk]:
        chunks: list[ContextChunk] = []
        if not queries_dir.exists():
            return chunks
        for path in sorted(queries_dir.glob("*.sql")):
            try:
                sql_text = path.read_text()
            except OSError:
                continue
            chunks.extend(parse_query_patterns(sql_text))
        return chunks
