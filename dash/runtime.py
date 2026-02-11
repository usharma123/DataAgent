"""Unified runtime wiring — process-wide singleton for VaultOrchestrator."""

from dash.native.runtime import get_native_orchestrator
from dash.orchestrator import VaultOrchestrator
from dash.personal.learning import PersonalReflectionEngine
from dash.personal.runtime import get_memory_manager, get_personal_orchestrator, get_personal_store

_vault_orchestrator: VaultOrchestrator | None = None


def get_vault_orchestrator() -> VaultOrchestrator:
    """Return process-wide VaultOrchestrator singleton wiring both runtimes + shared memory."""
    global _vault_orchestrator
    if _vault_orchestrator is None:
        store = get_personal_store()
        _vault_orchestrator = VaultOrchestrator(
            native=get_native_orchestrator(),
            personal=get_personal_orchestrator(),
            store=store,
            memory_manager=get_memory_manager(),
            reflection_engine=PersonalReflectionEngine(),
        )
    return _vault_orchestrator
