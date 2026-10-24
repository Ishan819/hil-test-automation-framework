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
