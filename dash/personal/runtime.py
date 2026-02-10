"""Runtime wiring for personal data agent components."""

from os import getenv

from dash.personal.evals import MemoryEvalRunner
from dash.personal.learning import PersonalReflectionEngine
from dash.personal.memory import MemoryManager
from dash.personal.orchestrator import PersonalOrchestrator
from dash.personal.retrieval import PersonalRetriever
from dash.personal.store import PersonalStore

_personal_store: PersonalStore | None = None
_personal_orchestrator: PersonalOrchestrator | None = None
_memory_manager: MemoryManager | None = None
_memory_eval_runner: MemoryEvalRunner | None = None


def _resolve_personal_db_url(override: str | None = None) -> str:
    if override:
        return override
    explicit = getenv("DASH_PERSONAL_DB_URL", "").strip()
    if explicit:
        return explicit
    return "sqlite+pysqlite:///./personal_dash.db"


def get_personal_store(database_url: str | None = None) -> PersonalStore:
    """Return process-wide personal store singleton."""
    if database_url is not None:
        return PersonalStore(database_url=database_url)

    global _personal_store
    if _personal_store is None:
        _personal_store = PersonalStore(database_url=_resolve_personal_db_url())
    return _personal_store


def get_memory_manager(database_url: str | None = None) -> MemoryManager:
    """Return process-wide memory manager singleton."""
    if database_url is not None:
        return MemoryManager(store=get_personal_store(database_url=database_url))

    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager(store=get_personal_store())
    return _memory_manager


def get_personal_orchestrator(database_url: str | None = None) -> PersonalOrchestrator:
    """Return process-wide personal orchestrator singleton."""
    if database_url is not None:
        store = get_personal_store(database_url=database_url)
        return PersonalOrchestrator(
            store=store,
            retriever=PersonalRetriever(store=store),
            memory_manager=MemoryManager(store=store),
            reflection_engine=PersonalReflectionEngine(),
        )

    global _personal_orchestrator
    if _personal_orchestrator is None:
        store = get_personal_store()
        _personal_orchestrator = PersonalOrchestrator(
            store=store,
            retriever=PersonalRetriever(store=store),
            memory_manager=get_memory_manager(),
            reflection_engine=PersonalReflectionEngine(),
        )
    return _personal_orchestrator


def get_memory_eval_runner(database_url: str | None = None) -> MemoryEvalRunner:
    """Return process-wide memory eval runner singleton."""
    if database_url is not None:
        return MemoryEvalRunner(store=get_personal_store(database_url=database_url))

    global _memory_eval_runner
    if _memory_eval_runner is None:
        _memory_eval_runner = MemoryEvalRunner(store=get_personal_store())
    return _memory_eval_runner
