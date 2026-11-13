"""Regression cases found during the final execution and evidence audit."""
import subprocess
import sys
from pathlib import Path

import pytest

from hil_automation.config import Suite, TestCase as HilTestCase, load_suite
from hil_automation.plans import load_plan
from hil_automation.qualification import evaluate_qualification
from hil_automation.qualification_policy import QualificationPolicy
from hil_automation.runner import run_suite


@pytest.mark.parametrize("duplicate", [
    "tests: [{name: dropped, steps: [{action: expect_temperature_below, limit_c: 0}]}]\n",
    "suite: replaced\n",
])
def test_duplicate_suite_fields_cannot_replace_inventory(tmp_path, duplicate):
    path = tmp_path / "suite.yaml"
    path.write_text(duplicate + "suite: audit\nbench: {type: simulated}\n"
                    "tests: [{name: healthy, steps: [{action: expect_heartbeat}]}]\n")
    with pytest.raises(ValueError, match="Invalid YAML"):
        load_suite(path)


@pytest.mark.parametrize("step", [
    "{action: expect_temperature_below, limit_c: 0, limit_c: 75}",
    "{action: expect_temperature_below, action: expect_heartbeat, limit_c: 0}",
])
def test_duplicate_nested_parameters_cannot_change_outcomes(tmp_path, step):
    path = tmp_path / "suite.yaml"
    path.write_text(f"suite: audit\nbench: {{type: simulated}}\ntests:\n"
                    f"  - name: thermal\n    steps: [{step}]\n")
    with pytest.raises(ValueError, match="Invalid YAML"):
        load_suite(path)


def test_duplicate_plan_inventory_is_a_cli_configuration_error(tmp_path):
    root = Path(__file__).resolve().parents[1]
    path = tmp_path / "plan.yaml"
    path.write_text(f"plan: audit\nsuites: ['{root / 'scenarios/faults.yaml'}']\n"
                    "suites: [healthy.yaml]\n")
    (tmp_path / "healthy.yaml").write_text("suite: healthy\nbench: {type: simulated}\n"
                                           "tests: [{name: alive, steps: [{action: expect_heartbeat}]}]\n")
    output = tmp_path / "reports"
    result = subprocess.run([sys.executable, "-m", "hil_automation.cli", "--plan", str(path),
                             "--report-dir", str(output)], capture_output=True, text=True)
    assert result.returncode == 2
    assert "Invalid plan YAML" in result.stderr
    assert not result.stdout and not output.exists()


@pytest.mark.parametrize("retained", [1, 2, 3])
def test_unexhausted_retry_history_cannot_qualify_even_under_permissive_policy(retained):
    suite = Suite("audit", {"type": "simulated"}, [HilTestCase(
        "fault", [{"action": "expect_temperature_below", "limit_c": 0}], retries=3,
    )])
    report = run_suite(suite)
    policy = QualificationPolicy(0, 10, True, True)
    assert evaluate_qualification(report, policy, expected=suite).qualified
    case = report.results[0]
    case.attempts = case.attempts[:retained]
    case.steps = case.attempts[-1].steps
    case.duration_ms = round(sum(attempt.duration_ms for attempt in case.attempts), 3)
    result = evaluate_qualification(report, policy, expected=suite)
    assert not result.qualified and not result.complete
    assert result.metrics.incomplete_cases == 1


def test_yaml_aliases_and_explicit_overrides_of_merge_defaults_still_work(tmp_path):
    path = tmp_path / "suite.yaml"
    path.write_text("""suite: merges
bench: {type: simulated}
defaults: &defaults {action: expect_temperature_below, limit_c: 0}
steps: &steps [{<<: *defaults, limit_c: 75}]
tests:
  - {name: one, steps: *steps}
  - {name: two, steps: *steps}
""")
    report = run_suite(load_suite(path))
    assert report.passed == 2 and report.failed == 0


def test_duplicate_fields_inside_inline_merge_are_also_rejected(tmp_path):
    path = tmp_path / "suite.yaml"
    path.write_text("suite: merge\nbench: {type: simulated}\ntests:\n"
                    "  - name: thermal\n    steps: [{<<: {action: expect_temperature_below, limit_c: 0, limit_c: 75}}]\n")
    with pytest.raises(ValueError, match="Invalid YAML"):
        load_suite(path)


def test_early_success_and_nonretryable_failure_are_complete(monkeypatch):
    from hil_automation import runner

    suite = Suite("audit", {"type": "simulated"}, [HilTestCase(
        "healthy", [{"action": "expect_heartbeat"}], retries=3,
    )])
    policy = QualificationPolicy(0, 10, True, True)
    assert evaluate_qualification(run_suite(suite), policy, expected=suite).qualified
    def nonretryable(bench, step):
        raise AssertionError("Nonretryable assertion")
    monkeypatch.setattr(runner, "execute_step", nonretryable)
    report = run_suite(suite)
    assert len(report.results[0].attempts) == 1
    assert not report.results[0].attempts[0].retryable
    assert evaluate_qualification(report, policy, expected=suite).qualified
