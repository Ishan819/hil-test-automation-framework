from dataclasses import asdict

from hil_automation.config import Suite, TestCase as HilTestCase
from hil_automation.runner import CaseResult, StepResult, run_suite


def test_step_model_and_independent_case_defaults():
    step = StepResult(1, "expect_heartbeat", "passed", "Step passed")
    first = CaseResult("first", "passed", 0, "All steps passed")
    second = CaseResult("second", "passed", 0, "All steps passed")
    first.steps.append(step)
    assert second.steps == []
    assert asdict(first)["steps"] == [{
        "index": 1, "action": "expect_heartbeat", "status": "passed", "details": "Step passed",
    }]


def test_successful_steps_are_recorded_in_order():
    report = run_suite(Suite("tracking", {}, [HilTestCase("healthy", [
        {"action": "set_voltage", "value": 5}, {"action": "expect_heartbeat"},
    ])]))
    assert [(step.index, step.action, step.status) for step in report.results[0].steps] == [
        (1, "set_voltage", "passed"), (2, "expect_heartbeat", "passed"),
    ]
    assert report.results[0].details == "All steps passed"


def test_failed_step_keeps_diagnostic_and_case_failure():
    report = run_suite(Suite("tracking", {}, [HilTestCase("lost", [
        {"action": "set_connection", "connected": False}, {"action": "expect_heartbeat"},
    ])]))
    case = report.results[0]
    assert [step.status for step in case.steps] == ["passed", "failed"]
    assert case.details == f"Step 2: {case.steps[1].details}"
    assert "heartbeat" in case.steps[1].details
    assert (report.passed, report.failed) == (0, 1)


def test_later_steps_are_skipped_without_execution(monkeypatch):
    from hil_automation import runner

    calls = []
    execute = runner.execute_step

    def record(bench, step):
        calls.append(step["action"])
        execute(bench, step)

    monkeypatch.setattr(runner, "execute_step", record)
    case = run_suite(Suite("tracking", {"connected": False}, [HilTestCase("lost", [
        {"action": "expect_heartbeat"}, {"action": "set_connection", "connected": True},
        {"action": "expect_heartbeat"},
    ])])).results[0]
    assert calls == ["expect_heartbeat"]
    assert [step.status for step in case.steps] == ["failed", "skipped", "skipped"]
    assert case.steps[1].details == "Earlier step failed"
