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
