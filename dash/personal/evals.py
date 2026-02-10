"""Memory-focused evaluation helpers for personal runtime."""

from dataclasses import dataclass
from uuid import uuid4

from dash.personal.store import PersonalStore


@dataclass(frozen=True)
class MemoryEvalSummary:
    """Computed memory efficacy metrics."""

    run_id: str
    repeated_error_reduction_pct: float
    avg_retry_reduction_pct: float
    citation_compliance_pct: float
    runs_analyzed: int


class MemoryEvalRunner:
    """Evaluate memory impact based on persisted run telemetry."""

    def __init__(self, store: PersonalStore):
        self._store = store

    def run(self) -> MemoryEvalSummary:
        """Compute and persist a memory quality summary."""
        stats = self._store.memory_eval_window()
        runs_analyzed = max(1, int(stats.get("total_runs", 0)))
        success_runs = int(stats.get("success_runs", 0))
        repeated_failures = int(stats.get("repeated_failures", 0))
        runs_with_memory = int(stats.get("runs_with_memory", 0))
        memory_applied_events = int(stats.get("memory_applied_events", 0))
        runs_with_citations = int(stats.get("runs_with_citations", 0))

        # Conservative proxy metrics from available telemetry.
        repeated_error_reduction_pct = round(max(0.0, 100.0 - ((repeated_failures / runs_analyzed) * 100.0)), 2)
        avg_retry_reduction_pct = round(min(100.0, (memory_applied_events / runs_analyzed) * 25.0), 2)
        citation_compliance_pct = round((runs_with_citations / runs_analyzed) * 100.0, 2)

        summary = MemoryEvalSummary(
            run_id=str(uuid4()),
            repeated_error_reduction_pct=repeated_error_reduction_pct,
            avg_retry_reduction_pct=avg_retry_reduction_pct,
            citation_compliance_pct=citation_compliance_pct,
            runs_analyzed=int(stats.get("total_runs", 0)),
        )
        payload = {
            "summary": {
                "repeated_error_reduction_pct": repeated_error_reduction_pct,
                "avg_retry_reduction_pct": avg_retry_reduction_pct,
                "citation_compliance_pct": citation_compliance_pct,
                "runs_analyzed": int(stats.get("total_runs", 0)),
            },
            "stats": {
                "total_runs": int(stats.get("total_runs", 0)),
                "success_runs": success_runs,
                "runs_with_memory": runs_with_memory,
                "memory_applied_events": memory_applied_events,
                "repeated_failures": repeated_failures,
                "runs_with_citations": runs_with_citations,
            },
        }
        self._store.create_memory_eval_run(run_id=summary.run_id, status="success", payload=payload)
        return summary
