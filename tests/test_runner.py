from pathlib import Path

import pytest

from hil_automation.config import Suite, TestCase as HilTestCase, load_suite
from hil_automation.runner import run_suite


SCENARIOS = Path(__file__).resolve().parents[1] / "scenarios"


def test_smoke_scenario_passes():
    report = run_suite(load_suite(SCENARIOS / "smoke.yaml"))
    assert (report.passed, report.failed) == (3, 0)
    assert all(case.status == "passed" for case in report.results)


def test_failure_scenario_reports_the_reason():
    report = run_suite(load_suite(SCENARIOS / "failure_demo.yaml"))
    assert (report.passed, report.failed) == (0, 2)
    assert "Temperature" in report.results[0].details
    assert "heartbeat" in report.results[1].details


def test_voltage_mismatch_is_reported():
    suite = Suite("bad-voltage", {"type": "simulated"}, [
        HilTestCase("voltage", [{"action": "expect_voltage", "value": 5, "tolerance": 0.1}])
    ])
    result = run_suite(suite)
    assert result.failed == 1
    assert "expected 5.00" in result.results[0].details


def test_each_test_starts_with_a_clean_bench():
    suite = Suite("isolation", {"type": "simulated"}, [
        HilTestCase("change", [{"action": "set_voltage", "value": 5}]),
        HilTestCase("check_initial", [{"action": "expect_voltage", "value": 0, "tolerance": 0}]),
    ])
    assert run_suite(suite).passed == 2


def test_unknown_action_is_rejected(tmp_path):
    config = tmp_path / "invalid.yaml"
    config.write_text("""suite: bad
bench: {type: simulated}
tests:
  - name: bad-step
    steps:
      - action: turn_on_rocket
""")
    with pytest.raises(ValueError, match="Unknown action"):
        load_suite(config)


def test_negative_tolerance_is_rejected(tmp_path):
    config = tmp_path / "invalid.yaml"
    config.write_text("""suite: bad
bench: {type: simulated}
tests:
  - name: bad-step
    steps:
      - {action: expect_voltage, value: 5, tolerance: -1}
""")
    with pytest.raises(ValueError, match="tolerance"):
        load_suite(config)


def test_temperature_changes_reach_bench():
    from hil_automation.bench import SimulatedBench
    from hil_automation.runner import execute_step

    bench = SimulatedBench()
    execute_step(bench, {"action": "set_temperature", "value": 65.5})
    assert bench.read_temperature_c() == 65.5


def test_temperature_overheating_and_isolation():
    suite = Suite("thermal", {"type": "simulated", "temperature_c": 35}, [
        HilTestCase("overheat", [
            {"action": "set_temperature", "value": 95},
            {"action": "expect_temperature_below", "limit_c": 80},
            {"action": "set_temperature", "value": 20},
        ]),
        HilTestCase("fresh", [
            {"action": "expect_temperature_below", "limit_c": 36},
        ]),
        HilTestCase("cool", [
            {"action": "set_temperature", "value": 25},
            {"action": "expect_temperature_below", "limit_c": 30},
        ]),
    ])
    report = run_suite(suite)
    assert (report.passed, report.failed) == (2, 1)
    assert report.results[0].details == "Step 2: Temperature 95.0 °C exceeds limit"


def test_temperature_limit_is_strict():
    suite = Suite("boundary", {}, [HilTestCase("equal", [
        {"action": "set_temperature", "value": 80},
        {"action": "expect_temperature_below", "limit_c": 80},
    ])])
    assert run_suite(suite).failed == 1


def test_lost_connection_fails_and_next_case_is_connected():
    suite = Suite("connection", {}, [
        HilTestCase("lost", [
            {"action": "set_connection", "connected": False},
            {"action": "expect_heartbeat"},
            {"action": "set_connection", "connected": True},
        ]),
        HilTestCase("fresh", [{"action": "expect_heartbeat"}]),
    ])
    report = run_suite(suite)
    assert (report.passed, report.failed) == (1, 1)
    assert report.results[0].details == "Step 2: Device heartbeat not detected"


def test_connection_can_be_restored():
    suite = Suite("recovery", {"connected": False}, [
        HilTestCase("restored", [
            {"action": "set_connection", "connected": True},
            {"action": "expect_heartbeat"},
        ]),
        HilTestCase("initially-disconnected", [{"action": "expect_heartbeat"}]),
    ])
    report = run_suite(suite)
    assert [result.status for result in report.results] == ["passed", "failed"]


def test_connection_changes_reach_bench():
    from hil_automation.bench import SimulatedBench
    from hil_automation.runner import execute_step

    bench = SimulatedBench()
    execute_step(bench, {"action": "set_connection", "connected": False})
    assert bench.heartbeat_ok() is False
    execute_step(bench, {"action": "set_connection", "connected": True})
    assert bench.heartbeat_ok() is True


@pytest.mark.parametrize("value", [True, "28", None, float("nan"), float("inf"), -41, 151])
def test_make_bench_rejects_invalid_initial_temperature(value):
    from hil_automation.runner import make_bench

    with pytest.raises(ValueError, match="Temperature must be a finite number"):
        make_bench({"temperature_c": value})
