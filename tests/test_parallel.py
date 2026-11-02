from pathlib import Path
from threading import Barrier, Lock

import pytest

from hil_automation import orchestration
from hil_automation.config import Suite, TestCase as HilTestCase
from hil_automation.plans import ExecutionPlan, PlanSuite


def entry(name, steps=None, retries=0):
    return PlanSuite(Path(f"{name}.yaml"), Suite(name, {}, [
        HilTestCase(name, steps or [{"action": "expect_heartbeat"}], retries=retries),
    ]))


@pytest.mark.parametrize("workers", [2, 3])
def test_parallel_workers_overlap_and_stay_bounded(monkeypatch, workers):
    original = orchestration.run_suite
    barrier = Barrier(workers)
    lock = Lock()
    active = peak = 0

    def run(suite):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            barrier.wait(timeout=10)
            return original(suite)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(orchestration, "run_suite", run)
    batch = orchestration.run_plan(ExecutionPlan("overlap", [entry(str(i)) for i in range(workers * 2)], workers))
    assert batch.status == "passed"
    assert peak == workers
    assert active == 0
    assert len({suite.report.run_id for suite in batch.suites}) == workers * 2


def test_parallel_fail_fast_is_rejected_before_execution(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Invalid combinations must not execute")
    monkeypatch.setattr(orchestration, "run_suite", unexpected)
    with pytest.raises(ValueError, match="does not support fail-fast"):
        orchestration.run_plan(ExecutionPlan("fast", [entry("one")], 2), fail_fast=True)


def test_parallel_rejects_non_simulated_benches():
    suite = PlanSuite(Path("device.yaml"), Suite("device", {"type": "physical"}, []))
    with pytest.raises(ValueError, match="only software-simulated"):
        orchestration.run_plan(ExecutionPlan("unsafe", [suite], 2))


def test_out_of_order_completion_preserves_plan_associations(monkeypatch):
    from threading import Event

    original = orchestration.run_suite
    last_finished = Event()
    completed = []

    def run(suite):
        if suite.name == "first":
            assert last_finished.wait(timeout=10)
        report = original(suite)
        completed.append(suite.name)
        if suite.name == "last":
            last_finished.set()
        return report

    monkeypatch.setattr(orchestration, "run_suite", run)
    batch = orchestration.run_plan(ExecutionPlan("ordered", [
        entry("first"), entry("middle"), entry("last"),
    ], 2))
    assert completed.index("last") < completed.index("first")
    assert [suite.name for suite in batch.suites] == ["first", "middle", "last"]
    assert [suite.report.suite for suite in batch.suites] == ["first", "middle", "last"]
    assert [suite.report.results[0].name for suite in batch.suites] == ["first", "middle", "last"]


@pytest.mark.parametrize("workers", [0, -1, 9, True, False, 2.0, "2"])
def test_worker_overrides_are_validated_before_execution(monkeypatch, workers):
    def unexpected(*args, **kwargs):
        pytest.fail("Invalid workers must not execute")
    monkeypatch.setattr(orchestration, "run_suite", unexpected)
    with pytest.raises(ValueError, match="Workers must be an integer"):
        orchestration.run_plan(ExecutionPlan("invalid", [entry("one")]), workers=workers)


def test_default_execution_stays_on_calling_thread(monkeypatch):
    from threading import get_ident

    original = orchestration.run_suite
    caller = get_ident()
    observed = []
    def run(suite, **kwargs):
        observed.append((suite.name, get_ident(), kwargs))
        return original(suite, **kwargs)
    monkeypatch.setattr(orchestration, "run_suite", run)
    orchestration.run_plan(ExecutionPlan("default", [entry("first"), entry("second")]))
    assert observed == [("first", caller, {"fail_fast": False}), ("second", caller, {"fail_fast": False})]


def test_one_worker_override_preserves_sequential_fail_fast():
    plan = ExecutionPlan("override", [
        entry("fault", [{"action": "expect_temperature_below", "limit_c": 0}]), entry("later"),
    ], 2)
    batch = orchestration.run_plan(plan, workers=1, fail_fast=True)
    assert [suite.status for suite in batch.suites] == ["failed", "skipped"]


def test_single_suite_accepts_maximum_workers():
    batch = orchestration.run_plan(ExecutionPlan("small", [entry("one")], 8))
    assert len(batch.suites) == 1 and batch.status == "passed"


def test_empty_plan_is_rejected():
    with pytest.raises(ValueError, match="at least one suite"):
        orchestration.run_plan(ExecutionPlan("empty", [], 2))


def test_worker_exception_is_not_mistaken_for_a_passing_batch(monkeypatch):
    def broken(suite):
        raise RuntimeError("worker bug")
    monkeypatch.setattr(orchestration, "run_suite", broken)
    batch = orchestration.run_plan(ExecutionPlan("broken", [entry("one")], 2))
    assert batch.status == "failed"
    assert batch.suites[0].report is None
    assert batch.suites[0].error == "RuntimeError: worker bug"


def test_parallel_snapshots_do_not_share_mutable_suite_inputs(monkeypatch):
    original = orchestration.run_suite
    barrier = Barrier(2)
    observed = []
    shared = entry("shared")

    def run(suite):
        observed.append(suite)
        suite.bench["private"] = id(suite)
        suite.tests[0].steps[0]["private"] = id(suite)
        barrier.wait(timeout=10)
        assert suite.bench["private"] == id(suite)
        assert suite.tests[0].steps[0]["private"] == id(suite)
        return original(suite)

    monkeypatch.setattr(orchestration, "run_suite", run)
    batch = orchestration.run_plan(ExecutionPlan("aliases", [shared, shared], 2))
    assert len({id(suite) for suite in observed}) == 2
    assert shared.suite.bench == {}
    assert shared.suite.tests[0].steps == [{"action": "expect_heartbeat"}]
    batch.suites[0].report.results[0].steps[0].details = "changed"
    assert batch.suites[1].report.results[0].steps[0].details == "Step passed"
    assert batch.suites[0].report.results[0].attempts[0].steps[0].details == "Step passed"


def test_concurrent_benches_and_retry_histories_are_independent(monkeypatch):
    original = orchestration.run_suite
    barrier = Barrier(3)
    def run(suite):
        barrier.wait(timeout=10)
        return original(suite)
    monkeypatch.setattr(orchestration, "run_suite", run)
    plan = ExecutionPlan("isolation", [
        entry("mutate", [
            {"action": "set_voltage", "value": 12},
            {"action": "set_temperature", "value": 95},
            {"action": "set_connection", "connected": False},
        ]),
        entry("fresh", [
            {"action": "expect_voltage", "value": 0, "tolerance": 0},
            {"action": "expect_temperature_below", "limit_c": 30},
            {"action": "expect_heartbeat"},
        ], retries=3),
        entry("retry", [{"action": "expect_temperature_below", "limit_c": 0}], retries=2),
    ], 3)
    batch = orchestration.run_plan(plan)
    assert [suite.status for suite in batch.suites] == ["passed", "passed", "failed"]
    cases = [suite.report.results[0] for suite in batch.suites]
    assert [len(case.attempts) for case in cases] == [1, 1, 3]
    assert [attempt.number for attempt in cases[2].attempts] == [1, 2, 3]
    assert all("28.0" in attempt.details for attempt in cases[2].attempts)
    assert len({id(case.attempts) for case in cases}) == 3
