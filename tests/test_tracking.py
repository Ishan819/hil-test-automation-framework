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
