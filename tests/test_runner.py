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
