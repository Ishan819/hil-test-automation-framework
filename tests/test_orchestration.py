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


def test_batch_statistics_include_unexecuted_cases():
    batch = run_plan(ExecutionPlan("counts", [
        entry("fault", [{"action": "expect_temperature_below", "limit_c": 0}]),
        entry("later", [{"action": "expect_heartbeat"}]),
    ]), fail_fast=True)
    stats = batch.to_dict()["statistics"]
    assert stats == {
        "total_suites": 2, "executed_suites": 1, "passed_suites": 0,
        "failed_suites": 1, "skipped_suites": 1, "total_cases": 2,
        "executed_cases": 1, "passed_cases": 0, "failed_cases": 1, "skipped_cases": 1,
    }


def test_per_suite_reports_cannot_collide_or_overwrite_previous_batches(tmp_path):
    import json
    import pytest
    from hil_automation.orchestration import write_batch_report
    from hil_automation.reporting import ReportError

    first = entry("same", [{"action": "expect_heartbeat"}])
    second = PlanSuite(Path("other.yaml"), first.suite)
    plan = ExecutionPlan("duplicates", [first, second])
    batch = run_plan(plan)
    manifest = write_batch_report(batch, str(tmp_path))
    payload = json.loads(manifest.read_text())
    assert [suite["report_file"] for suite in payload["suites"]] == ["001.json", "002.json"]
    reports = [json.loads((manifest.parent / suite["report_file"]).read_text()) for suite in payload["suites"]]
    assert len({report["run_id"] for report in reports}) == 2
    with pytest.raises(ReportError, match="Cannot write batch report"):
        write_batch_report(batch, str(tmp_path))
    other = write_batch_report(run_plan(plan), str(tmp_path))
    assert other.parent != manifest.parent
    assert json.loads(manifest.read_text()) == payload
