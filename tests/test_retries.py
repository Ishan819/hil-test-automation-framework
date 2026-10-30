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


def test_retry_limit_means_additional_attempts_with_fresh_benches(monkeypatch):
    from hil_automation import runner

    benches = []
    original = runner.make_bench

    def make(config):
        bench = original(config)
        benches.append(bench)
        return bench

    monkeypatch.setattr(runner, "make_bench", make)
    case = run_suite(Suite("retry", {}, [
        HilTestCase("fails", [{"action": "expect_temperature_below", "limit_c": 0}], retries=2),
    ])).results[0]
    assert [attempt.number for attempt in case.attempts] == [1, 2, 3]
    assert len({id(bench) for bench in benches}) == 3
    assert all(attempt.status == "failed" for attempt in case.attempts)
    assert case.duration_ms == round(sum(attempt.duration_ms for attempt in case.attempts), 3)


def test_configuration_errors_are_not_retried():
    case = run_suite(Suite("invalid", {}, [
        HilTestCase("bad-action", [{"action": "unknown"}], retries=3),
    ])).results[0]
    assert len(case.attempts) == 1
    assert case.failure_category == "invalid_test_configuration"


def test_unexpected_programming_exceptions_are_not_retried(monkeypatch):
    from hil_automation import runner

    calls = []
    def bug(bench, step):
        calls.append(step)
        raise RuntimeError("unexpected bug")
    monkeypatch.setattr(runner, "execute_step", bug)
    with pytest.raises(RuntimeError, match="unexpected bug"):
        run_suite(Suite("bug", {}, [
            HilTestCase("bug", [{"action": "expect_heartbeat"}], retries=3),
        ]))
    assert len(calls) == 1


def test_later_success_is_visible_and_prior_failure_is_preserved(monkeypatch):
    from hil_automation import runner

    original = runner.make_bench
    benches = []
    def make(config):
        bench = original(config)
        if not benches:
            bench.set_temperature(95)
        benches.append(bench)
        return bench
    monkeypatch.setattr(runner, "make_bench", make)
    report = run_suite(Suite("recovers", {}, [
        HilTestCase("thermal", [{"action": "expect_temperature_below", "limit_c": 75}], retries=3),
    ]))
    case = report.results[0]
    assert [attempt.status for attempt in case.attempts] == ["failed", "passed"]
    assert "95.0" in case.attempts[0].details
    assert case.passed_after_retry and case.retry_count == 1
    assert case.details == "Passed on attempt 2 after retry"
    data = report.to_dict()["results"][0]
    assert data["passed_after_retry"] is True and data["retry_count"] == 1
    assert data["attempts"][0]["status"] == "failed"
    assert report.passed == 1 and report.failed == 0
