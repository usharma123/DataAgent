"""
Run evaluations against the Data Agent.

Usage:
    python -m da.evals.run_evals
    python -m da.evals.run_evals --category basic
"""

import argparse
import time

from da.evals.test_cases import CATEGORIES, TEST_CASES

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Data Agent evaluations")
    parser.add_argument("--category", "-c", choices=CATEGORIES, help="Filter by category")
    args = parser.parse_args()

    from da.agent import data_agent

    # Filter tests
    tests = TEST_CASES
    if args.category:
        tests = [(q, e, c) for q, e, c in tests if c == args.category]

    print(f"Running {len(tests)} tests...\n")

    passed = 0
    failed = 0
    start = time.time()

    for question, expected, category in tests:
        print(f"[{category}] {question[:50]}...", end=" ", flush=True)

        try:
            result = data_agent.run(question)
            response = (result.content or "").lower()
            missing = [v for v in expected if v.lower() not in response]

            if missing:
                print(f"FAIL (missing: {missing})")
                failed += 1
            else:
                print("PASS")
                passed += 1
        except Exception as e:
            print(f"ERROR: {e}")
            failed += 1

    duration = time.time() - start
    total = passed + failed
    rate = (passed / total * 100) if total else 0

    print(f"\nResults: {passed}/{total} passed ({rate:.0f}%) in {duration:.1f}s")
