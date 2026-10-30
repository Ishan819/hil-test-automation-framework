from pathlib import Path

from hil_automation.config import Suite, TestCase as HilTestCase
from hil_automation.orchestration import run_plan
from hil_automation.plans import ExecutionPlan, PlanSuite


def entry(name, steps, retries=0):
    return PlanSuite(Path(f"{name}.yaml"), Suite(name, {}, [
        HilTestCase(name, steps, retries=retries),
    ]))


def test_plan_runs_sequentially_with_independent_state_and_run_ids(monkeypatch):
    from hil_automation import orchestration

    original = orchestration.run_suite
    order = []
    def run(suite, **kwargs):
        order.append(suite.name)
        return original(suite, **kwargs)
    monkeypatch.setattr(orchestration, "run_suite", run)
    plan = ExecutionPlan("ordered", [
        entry("mutate", [
            {"action": "set_voltage", "value": 5},
            {"action": "set_temperature", "value": 95},
            {"action": "set_connection", "connected": False},
        ]),
        entry("fresh", [
            {"action": "expect_voltage", "value": 0, "tolerance": 0},
            {"action": "expect_temperature_below", "limit_c": 30},
            {"action": "expect_heartbeat"},
        ]),
    ])
    batch = run_plan(plan)
    assert order == ["mutate", "fresh"]
    assert batch.status == "passed"
    assert all(suite.report.passed == 1 for suite in batch.suites)
    assert len({batch.run_id, *(suite.report.run_id for suite in batch.suites)}) == 3


def test_plan_fail_fast_preserves_failed_run_and_marks_unexecuted_suites():
    plan = ExecutionPlan("fast", [
        entry("fault", [{"action": "expect_temperature_below", "limit_c": 0}], retries=1),
        entry("later", [{"action": "expect_heartbeat"}]),
    ])
    batch = run_plan(plan, fail_fast=True)
    assert batch.status == "failed"
    assert [suite.status for suite in batch.suites] == ["failed", "skipped"]
    assert len(batch.suites[0].report.results[0].attempts) == 2
    assert batch.suites[1].report is None
    ordinary = run_plan(plan)
    assert [suite.status for suite in ordinary.suites] == ["failed", "passed"]
