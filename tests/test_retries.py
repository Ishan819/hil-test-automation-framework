import pytest

from hil_automation.config import Suite, TestCase as HilTestCase
from hil_automation.runner import run_suite


def test_first_attempt_is_recorded_independently_of_case_steps():
    case = run_suite(Suite("attempts", {}, [
        HilTestCase("healthy", [{"action": "expect_heartbeat"}]),
    ])).results[0]
    assert len(case.attempts) == 1
    attempt = case.attempts[0]
    assert (attempt.number, attempt.status, attempt.details) == (1, "passed", "All steps passed")
    assert attempt.duration_ms == case.duration_ms
    case.steps[0].details = "changed"
    assert attempt.steps[0].details == "Step passed"
