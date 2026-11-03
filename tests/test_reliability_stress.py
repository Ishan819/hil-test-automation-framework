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


def test_repeated_mixed_failures_preserve_later_work(monkeypatch):
    from hil_automation import orchestration
    original = orchestration.run_suite
    def execute(suite):
        if suite.name.startswith("exception"):
            raise RuntimeError("task unavailable")
        return original(suite)
    monkeypatch.setattr(orchestration, "run_suite", execute)
    entries = [entry("healthy"), entry("exception"), entry("assertion", [
        {"action": "expect_temperature_below", "limit_c": 0},
    ], retries=1), entry("later")]
    for _ in range(10):
        batch = run_plan(ExecutionPlan("mixed", entries * 4, 3))
        assert batch.status == "failed"
        assert [s.status for s in batch.suites] == ["passed", "failed", "failed", "passed"] * 4
        stats = batch.to_dict()["statistics"]
        assert (stats["passed_cases"], stats["failed_cases"], stats["unreported_cases"]) == (8, 4, 4)
        assert all(s.error == "RuntimeError: task unavailable" for s in batch.suites[1::4])


@pytest.mark.parametrize("failure", ["cancelled", "future", "submission"])
def test_executor_boundary_failures_never_return_success(monkeypatch, failure):
    from concurrent.futures import CancelledError, Future
    from hil_automation import orchestration

    class Executor:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def submit(self, *args):
            if failure == "submission":
                raise RuntimeError("executor unavailable")
            future = Future()
            if failure == "cancelled":
                future.cancel()
            else:
                future.set_exception(RuntimeError("executor unavailable"))
            return future

    # Fault injection at the executor boundary; production exposes no cancellation API.
    monkeypatch.setattr(orchestration, "ThreadPoolExecutor", Executor)
    monkeypatch.setattr(orchestration, "wait", lambda pending, **kwargs: (set(pending), set()))
    with pytest.raises(CancelledError if failure == "cancelled" else RuntimeError):
        run_plan(ExecutionPlan("interrupted", [entry(str(i)) for i in range(6)], 2))


def test_repeated_sequential_fail_fast_leaves_later_work_unstarted():
    from hil_automation.qualification import evaluate_qualification
    from hil_automation.qualification_policy import QualificationPolicy
    plan = ExecutionPlan("fail-fast", [entry("fails", [
        {"action": "expect_temperature_below", "limit_c": 0},
    ], retries=2), entry("unstarted")])
    for _ in range(8):
        batch = run_plan(plan, fail_fast=True)
        assert [s.status for s in batch.suites] == ["failed", "skipped"]
        assert batch.suites[1].report is None
        assert len(batch.suites[0].report.results[0].attempts) == 3
        assert not evaluate_qualification(batch, QualificationPolicy(), expected=plan).qualified
