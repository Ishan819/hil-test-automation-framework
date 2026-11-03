"""Bounded deterministic stress checks; no scheduling or timing expectations."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from hil_automation.orchestration import run_plan
from hil_automation.plans import ExecutionPlan
from test_parallel import entry


@pytest.mark.parametrize("workers", [2, 4, 8])
def test_repeated_parallel_execution_preserves_counts_and_identity(workers):
    plan = ExecutionPlan("repeat", [entry(str(i)) for i in range(17)], workers)
    ids = set()
    for _ in range(12):
        batch = run_plan(plan)
        assert batch.status == "passed"
        stats = batch.to_dict()["statistics"]
        assert stats["total_suites"] == stats["passed_suites"] == 17
        assert stats["total_cases"] == stats["passed_cases"] == 17
        assert [s.name for s in batch.suites] == [str(i) for i in range(17)]
        current = [batch.run_id, *(s.report.run_id for s in batch.suites)]
        assert len(set(current)) == 18
        assert not ids.intersection(current)
        ids.update(current)
        assert all(s.report.results[0].name == s.name for s in batch.suites)


def test_simultaneous_batches_keep_aggregation_independent():
    plan = ExecutionPlan("concurrent", [entry(str(i)) for i in range(9)], 3)
    with ThreadPoolExecutor(max_workers=3) as executor:
        batches = list(executor.map(lambda _: run_plan(plan), range(9)))
    assert len({b.run_id for b in batches}) == 9
    assert len({s.report.run_id for b in batches for s in b.suites}) == 81
    assert all(b.to_dict()["statistics"]["passed_cases"] == 9 for b in batches)
    batches[0].suites[0].report.results.clear()
    assert all(len(b.suites[0].report.results) == 1 for b in batches[1:])


def test_repeated_aliased_retry_inputs_and_histories_remain_isolated():
    shared = entry("retry", [
        {"action": "expect_voltage", "value": 0, "tolerance": 0},
        {"action": "set_voltage", "value": 12},
        {"action": "expect_temperature_below", "limit_c": 0},
    ], retries=2)
    plan = ExecutionPlan("aliases", [shared] * 8, 4)
    for _ in range(10):
        batch = run_plan(plan)
        assert batch.to_dict()["statistics"]["failed_cases"] == 8
        cases = [s.report.results[0] for s in batch.suites]
        assert all(len(c.attempts) == 3 for c in cases)
        assert all(a.steps[0].status == "passed" for c in cases for a in c.attempts)
        cases[0].attempts[0].steps[0].details = "private mutation"
        cases[0].steps[0].details = "final mutation"
        assert all(c.attempts[0].steps[0].details == "Step passed" for c in cases[1:])
        snapshot = batch.to_dict()
        snapshot["suites"][1]["report"]["results"][0]["attempts"].clear()
        assert len(cases[1].attempts) == 3
    assert shared.suite.bench == {}
    assert shared.suite.tests[0].steps[0] == {"action": "expect_voltage", "value": 0, "tolerance": 0}
