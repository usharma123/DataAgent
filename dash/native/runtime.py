"""Runtime wiring for native orchestrator components."""

from os import getenv

from dash.native.evals import NativeEvalRunner
from dash.native.executor import SqlExecutor
from dash.native.learning import LearningEngine
from dash.native.orchestrator import NativeOrchestrator
from dash.native.retrieval import LocalKnowledgeRetriever
from dash.native.sql_drafter import SqlDrafter
from dash.native.store import NativeRunStore

_orchestrator: NativeOrchestrator | None = None
_run_store: NativeRunStore | None = None
_eval_runner: NativeEvalRunner | None = None


def _resolve_database_url(override: str | None = None) -> str:
    if override:
        return override
    from db.url import db_url

    return getenv("VAULT_NATIVE_DB_URL", "").strip() or db_url


def get_native_run_store(database_url: str | None = None) -> NativeRunStore:
    """Return the process-wide run-store singleton."""
    if database_url is not None:
        return NativeRunStore(database_url=database_url)

    global _run_store
    if _run_store is None:
        _run_store = NativeRunStore(database_url=_resolve_database_url())
    return _run_store


def get_native_orchestrator(database_url: str | None = None) -> NativeOrchestrator:
    """Return the process-wide native orchestrator singleton."""
    if database_url is not None:
        return NativeOrchestrator(
            run_store=get_native_run_store(database_url=database_url),
            sql_executor=SqlExecutor(database_url=database_url),
            learning_engine=LearningEngine(),
            retriever=LocalKnowledgeRetriever(),
            sql_drafter=SqlDrafter(),
        )

    global _orchestrator
    if _orchestrator is None:
        runtime_db_url = _resolve_database_url()
        _orchestrator = NativeOrchestrator(
            run_store=get_native_run_store(database_url=runtime_db_url),
            sql_executor=SqlExecutor(database_url=runtime_db_url),
            learning_engine=LearningEngine(),
            retriever=LocalKnowledgeRetriever(),
            sql_drafter=SqlDrafter(),
        )
    return _orchestrator


def get_native_eval_runner(database_url: str | None = None) -> NativeEvalRunner:
    """Return the process-wide evaluation runner singleton."""
    if database_url is not None:
        store = get_native_run_store(database_url=database_url)
        orchestrator = get_native_orchestrator(database_url=database_url)
        return NativeEvalRunner(orchestrator=orchestrator, run_store=store)

    global _eval_runner
    if _eval_runner is None:
        _eval_runner = NativeEvalRunner(
            orchestrator=get_native_orchestrator(),
            run_store=get_native_run_store(),
        )
    return _eval_runner
