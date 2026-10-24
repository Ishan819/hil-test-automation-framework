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
        "index": 1, "action": "expect_heartbeat", "status": "passed", "details": "Step passed", "duration_ms": 0.0,
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


def test_step_timings_use_monotonic_timer_and_skips_take_zero(monkeypatch):
    from hil_automation import runner

    ticks = iter([9, 10, 11, 11.125, 12, 13])
    monkeypatch.setattr(runner, "perf_counter", lambda: next(ticks))
    case = run_suite(Suite("timing", {"connected": False}, [HilTestCase("lost", [
        {"action": "expect_heartbeat"}, {"action": "expect_heartbeat"},
    ])])).results[0]
    assert [step.duration_ms for step in case.steps] == [125, 0]
    assert case.duration_ms == 2000


def test_suite_timestamps_are_ordered_timezone_aware_utc():
    from datetime import datetime, timezone

    before = datetime.now(timezone.utc)
    report = run_suite(Suite("empty", {}, []))
    after = datetime.now(timezone.utc)
    started = datetime.fromisoformat(report.started_at)
    finished = datetime.fromisoformat(report.finished_at)
    assert before <= started <= finished <= after
    assert started.utcoffset().total_seconds() == 0
    assert finished.utcoffset().total_seconds() == 0


def test_each_run_has_a_unique_uuid():
    from uuid import UUID

    suite = Suite("repeat", {}, [HilTestCase("healthy", [{"action": "expect_heartbeat"}])])
    first, second = run_suite(suite), run_suite(suite)
    assert UUID(first.run_id).version == 4
    assert first.run_id != second.run_id
    assert first.to_dict()["run_id"] == first.run_id


def test_tracking_is_independent_across_cases_and_repeated_runs():
    suite = Suite("isolation", {}, [
        HilTestCase("fault", [
            {"action": "set_connection", "connected": False},
            {"action": "expect_heartbeat"}, {"action": "set_voltage", "value": 12},
        ]),
        HilTestCase("fresh", [{"action": "expect_heartbeat"}]),
    ])
    first, second = run_suite(suite), run_suite(suite)
    for report in (first, second):
        assert (report.passed, report.failed) == (1, 1)
        assert [step.status for step in report.results[0].steps] == [
            "passed", "failed", "skipped",
        ]
        assert report.results[1].steps[0].status == "passed"
        assert all(step.duration_ms >= 0 for case in report.results for step in case.steps)
    first.results[0].steps.clear()
    assert len(second.results[0].steps) == 3
    assert len(suite.tests[0].steps) == 3
