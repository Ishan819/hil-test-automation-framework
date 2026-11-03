import json
import sys

import pytest

from hil_automation.config import Suite, TestCase as HilTestCase
from hil_automation.orchestration import run_plan
from hil_automation.plans import ExecutionPlan
from hil_automation.qualification import evaluate_qualification
from hil_automation.qualification_policy import QualificationPolicy
from hil_automation.runner import run_suite
from test_batch_cli import ROOT
from test_parallel import entry


@pytest.mark.parametrize("field, value", [
    ("attempts", None), ("attempts", [{}]), ("steps", None), ("steps", []),
    ("duration_ms", float("nan")), ("duration_ms", True),
    ("details", ""), ("failure_category", "invalid_test_configuration"),
])
def test_corrupted_case_fields_prevent_qualification(field, value):
    suite = entry("corruption").suite
    report = run_suite(suite)
    setattr(report.results[0], field, value)
    result = evaluate_qualification(report, QualificationPolicy(0, 10, True, True), expected=suite)
    assert not result.qualified
    assert result.metrics.incomplete_cases == 1


@pytest.mark.parametrize("field, value", [
    ("retryable", True), ("number", True), ("failure_category", "assertion_failure"),
    ("details", ""), ("duration_ms", -1),
])
def test_corrupted_passing_attempts_prevent_qualification(field, value):
    suite = entry("attempt").suite
    report = run_suite(suite)
    setattr(report.results[0].attempts[0], field, value)
    assert not evaluate_qualification(report, QualificationPolicy(0, 10, True, True), expected=suite).qualified


def test_configuration_errors_cannot_be_accepted_as_ordinary_failed_cases():
    suite = entry("bad-config", [{"action": "unknown"}]).suite
    report = run_suite(suite)
    assert report.failed == 1
    result = evaluate_qualification(report, QualificationPolicy(0, 10), expected=suite)
    assert not result.qualified and not result.complete
    assert result.metrics.incomplete_cases == 1


@pytest.mark.parametrize("damage", ["schema", "outside_batch", "native", "id", "count", "unknown_status"])
def test_corrupted_execution_metadata_cannot_qualify(damage):
    plan = ExecutionPlan("metadata", [entry("healthy")])
    batch = run_plan(plan)
    report = batch.suites[0].report
    if damage == "schema":
        report.schema_version = "future"
    elif damage == "outside_batch":
        report.started_at = "2000-01-01T00:00:00+00:00"
    elif damage == "native":
        report.native_exit_code = 0
    elif damage == "id":
        report.run_id = "missing"
    elif damage == "count":
        report.passed = True
    else:
        report.results[0].status = "unknown"
    result = evaluate_qualification(batch, QualificationPolicy(0, 10, True, True), expected=plan)
    assert not result.qualified and result.issues


def test_unvalidated_json_is_not_accepted_as_completed_execution_evidence():
    suite = entry("raw-json").suite
    fake = run_suite(suite).to_dict()
    assert not evaluate_qualification(fake, QualificationPolicy(0, 10, True, True), expected=suite).qualified


def test_pass_percentage_decision_does_not_round_up_at_the_boundary():
    suite = Suite("thirds", {}, [
        HilTestCase("one", [{"action": "expect_heartbeat"}]),
        HilTestCase("two", [{"action": "expect_heartbeat"}]),
        HilTestCase("fault", [{"action": "expect_temperature_below", "limit_c": 0}]),
    ])
    report = run_suite(suite)
    assert evaluate_qualification(report, QualificationPolicy(66.66666666666666, 1), expected=suite).qualified
    assert not evaluate_qualification(report, QualificationPolicy(66.66666666666667, 1), expected=suite).qualified


@pytest.mark.parametrize("writer", ["write_batch_report", "write_qualification_report"])
def test_cli_report_errors_return_two_without_announcing_success(tmp_path, monkeypatch, capsys, writer):
    from hil_automation import cli
    from hil_automation.reporting import ReportError

    policy = tmp_path / "policy.yaml"
    policy.write_text("{}")
    root = tmp_path / "reports"
    def fail(*args, **kwargs):
        raise ReportError("simulated publication failure")
    monkeypatch.setattr(cli, writer, fail)
    monkeypatch.setattr(sys, "argv", ["hil-run", "--plan", str(ROOT / "plans/recovery.yaml"),
                                      "--qualification-policy", str(policy), "--report-dir", str(root)])
    assert cli.main() == 2
    captured = capsys.readouterr()
    assert "simulated publication failure" in captured.err
    assert not captured.out
    assert not list(root.glob("*/qualification.json"))


def test_cli_worker_failure_cannot_be_hidden_by_permissive_policy(tmp_path, monkeypatch, capsys):
    from hil_automation import cli, orchestration

    policy = tmp_path / "policy.yaml"
    policy.write_text("min_pass_percentage: 0\nmax_failed_cases: 100\nallow_skipped: true\nallow_recovered: true\n")
    root = tmp_path / "reports"
    original = orchestration.run_suite
    def run(suite):
        if suite.name == "bench-smoke-tests":
            raise RuntimeError("unexpected simulator exception")
        return original(suite)
    monkeypatch.setattr(orchestration, "run_suite", run)
    monkeypatch.setattr(sys, "argv", ["hil-run", "--plan", str(ROOT / "plans/recovery.yaml"), "--workers", "2",
                                      "--qualification-policy", str(policy), "--report-dir", str(root)])
    assert cli.main() == 1
    assert "Qualification: not qualified" in capsys.readouterr().out
    data = json.loads(next(root.glob("*/qualification.json")).read_text())
    assert not data["qualified"] and "worker_failure" in data["evidence_issues"]
    assert data["observed"]["incomplete_cases"] == data["observed"]["passed_cases"] == 3


@pytest.mark.parametrize("damage", ["step_index", "step_status", "category", "retryable"])
def test_damaged_retry_step_evidence_cannot_qualify(damage):
    suite = entry("retry-evidence", [
        {"action": "expect_temperature_below", "limit_c": 0},
    ], retries=1).suite
    report = run_suite(suite)
    case = report.results[0]
    if damage == "step_index":
        case.attempts[0].steps[0].index = True
    elif damage == "step_status":
        case.attempts[0].steps[0].status = "passed"
    elif damage == "category":
        case.attempts[0].steps[0].failure_category = "simulated_connection_failure"
    else:
        case.attempts[0].retryable = False
    result = evaluate_qualification(report, QualificationPolicy(0, 10, True, True), expected=suite)
    assert not result.qualified and not result.complete
    assert result.metrics.incomplete_cases == 1


def test_missing_batch_and_wrong_planned_suite_cannot_qualify():
    plan = ExecutionPlan("inventory", [entry("one")])
    policy = QualificationPolicy(0, 10, True, True)
    missing = evaluate_qualification(None, policy, expected=plan)
    assert not missing.qualified and "missing_batch_report" in missing.issues
    batch = run_plan(plan)
    batch.suites[0].case_count = 2
    wrong = evaluate_qualification(batch, policy, expected=plan)
    assert not wrong.qualified and "planned_suite_mismatch" in wrong.issues


def test_qualification_requires_validated_policy_object():
    with pytest.raises(ValueError, match="validated qualification policy"):
        evaluate_qualification(None, {}, expected=entry("one").suite)
