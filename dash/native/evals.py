"""Native evaluation runner."""

from dataclasses import dataclass
from time import perf_counter
from typing import Any
from uuid import uuid4

from dash.evals.test_cases import TEST_CASES, TestCase
from dash.native.contracts import AskRequest
from dash.native.orchestrator import NativeOrchestrator
from dash.native.store import NativeRunStore, NativeRunStoreError


@dataclass(frozen=True)
class NativeEvalSummary:
    """Summary of a native evaluation run."""

    run_id: str
    total: int
    passed: int
    failed: int
    duration_ms: int
    by_category: dict[str, dict[str, int]]


class NativeEvalRunner:
    """Runs regression checks against the native ask pipeline."""

    def __init__(self, orchestrator: NativeOrchestrator, run_store: NativeRunStore):
        self._orchestrator = orchestrator
        self._run_store = run_store

    def run(self, category: str | None = None) -> NativeEvalSummary:
        """Execute evaluations and persist summary into eval_runs."""
        tests = [tc for tc in TEST_CASES if category is None or tc.category == category]
        started = perf_counter()
        run_id = str(uuid4())
        passed = 0
        by_category: dict[str, dict[str, int]] = {}
        details: list[dict[str, Any]] = []

        for test in tests:
            ok, note = self._run_case(test)
            stats = by_category.setdefault(test.category, {"passed": 0, "failed": 0})
            if ok:
                passed += 1
                stats["passed"] += 1
            else:
                stats["failed"] += 1
            details.append({"question": test.question, "category": test.category, "passed": ok, "note": note})

        failed = len(tests) - passed
        duration_ms = int((perf_counter() - started) * 1000)
        summary = NativeEvalSummary(
            run_id=run_id,
            total=len(tests),
            passed=passed,
            failed=failed,
            duration_ms=duration_ms,
            by_category=by_category,
        )
        summary_text = (
            f"Native eval run completed: total={summary.total}, "
            f"passed={summary.passed}, failed={summary.failed}"
        )
        payload = {
            "summary": summary.__dict__,
            "details": details,
        }
        try:
            self._run_store.create_eval_run(
                run_id=run_id,
                status="success" if failed == 0 else "failed",
                summary=summary_text,
                results=payload,
            )
        except NativeRunStoreError:
            pass
        return summary

    def _run_case(self, test: TestCase) -> tuple[bool, str]:
        response = self._orchestrator.run_ask(AskRequest(question=test.question, include_debug=False))
        if response.status != "success":
            return False, response.error or "ask failed"

        searchable = f"{response.answer or ''}\n{response.rows or ''}".lower()
        missing = [value for value in test.expected_strings if value.lower() not in searchable]
        if missing:
            return False, f"missing expected strings: {', '.join(missing[:3])}"
        return True, "pass"
