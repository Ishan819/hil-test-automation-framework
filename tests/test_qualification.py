import pytest

from hil_automation.config import Suite
from hil_automation.orchestration import run_plan
from hil_automation.plans import ExecutionPlan
from hil_automation.qualification import evaluate_qualification
from hil_automation.qualification_policy import QualificationPolicy
from hil_automation.runner import run_suite
from test_parallel import entry


@pytest.mark.parametrize("workers", [1, 2])
def test_completed_actual_batch_qualifies(workers):
    plan = ExecutionPlan("release", [entry("one"), entry("two")], workers)
    batch = run_plan(plan)
    result = evaluate_qualification(batch, QualificationPolicy(), expected=plan)
    assert result.qualified and result.complete
    assert result.metrics.total_cases == result.metrics.passed_cases == 2
    assert result.metrics.pass_percentage == 100


def test_actual_suite_can_be_evaluated_independently():
    suite = entry("suite").suite
    result = evaluate_qualification(run_suite(suite), QualificationPolicy(), expected=suite)
    assert result.qualified
    assert result.references[0].kind == "suite"


def test_failures_obey_explicit_percentage_and_count_limits():
    plan = ExecutionPlan("mixed", [entry("pass"), entry("fail", [
        {"action": "expect_temperature_below", "limit_c": 0},
    ])])
    report = run_plan(plan)
    assert not evaluate_qualification(report, QualificationPolicy(), expected=plan).qualified
    assert evaluate_qualification(report, QualificationPolicy(50, 1), expected=plan).qualified
    assert not evaluate_qualification(report, QualificationPolicy(50.1, 1), expected=plan).qualified
    assert not evaluate_qualification(report, QualificationPolicy(50, 0), expected=plan).qualified


@pytest.mark.parametrize("damage", ["missing", "counts", "identity", "finished", "duplicate_id", "case"])
def test_inconsistent_evidence_never_qualifies_even_with_permissive_policy(damage):
    plan = ExecutionPlan("evidence", [entry("one"), entry("two")])
    batch = run_plan(plan)
    if damage == "missing":
        batch.suites.pop()
    elif damage == "counts":
        batch.suites[0].report.passed = 20
    elif damage == "identity":
        batch.suites[0].report.suite = "other"
    elif damage == "finished":
        batch.finished_at = ""
    elif damage == "duplicate_id":
        batch.suites[1].report.run_id = batch.suites[0].report.run_id
    else:
        batch.suites[0].report.results.clear()
    result = evaluate_qualification(batch, QualificationPolicy(0, 100, True, True), expected=plan)
    assert not result.qualified and not result.complete and result.issues


def test_missing_inventory_empty_and_missing_runs_do_not_qualify():
    suite = entry("one").suite
    policy = QualificationPolicy(0, 100, True, True)
    assert not evaluate_qualification(run_suite(suite), policy).qualified
    assert not evaluate_qualification(None, policy, expected=suite).qualified
    empty = Suite("empty", {}, [])
    assert not evaluate_qualification(run_suite(empty), policy, expected=empty).qualified


def test_skipped_cases_are_separate_from_failures_and_require_explicit_permission():
    from hil_automation.config import TestCase as HilTestCase

    suite = Suite("skips", {}, [
        HilTestCase("failure", [{"action": "expect_temperature_below", "limit_c": 0}]),
        HilTestCase("later", [{"action": "expect_heartbeat"}]),
    ])
    report = run_suite(suite, fail_fast=True)
    result = evaluate_qualification(report, QualificationPolicy(0, 1, True), expected=suite)
    assert result.qualified and result.complete
    assert (result.metrics.failed_cases, result.metrics.skipped_cases, result.metrics.incomplete_cases) == (1, 1, 0)
    denied = evaluate_qualification(report, QualificationPolicy(0, 1), expected=suite)
    assert not denied.qualified
    assert not next(item for item in denied.criteria if item.name == "allow_skipped").passed


def test_recovered_cases_are_counted_once_and_checked_against_policy(monkeypatch):
    from hil_automation import runner

    suite = entry("recover", [{"action": "expect_heartbeat"}], retries=2).suite
    original = runner.make_bench
    calls = []
    def make(config):
        bench = original(config)
        if not calls:
            bench.set_connected(False)
        calls.append(bench)
        return bench
    monkeypatch.setattr(runner, "make_bench", make)
    report = run_suite(suite)
    strict = evaluate_qualification(report, QualificationPolicy(), expected=suite)
    allowed = evaluate_qualification(report, QualificationPolicy(allow_recovered=True), expected=suite)
    assert not strict.qualified and allowed.qualified
    assert allowed.metrics.total_cases == allowed.metrics.passed_cases == allowed.metrics.recovered_cases == 1
    assert allowed.metrics.failed_cases == 0
    outcome = next(item for item in strict.criteria if item.name == "allow_recovered")
    assert (outcome.expected, outcome.observed, outcome.passed) == (False, 1, False)


@pytest.mark.parametrize("damage", ["number", "missing", "early_pass", "budget", "steps", "final"])
def test_corrupted_attempt_evidence_cannot_qualify(damage):
    suite = entry("attempts", [{"action": "expect_temperature_below", "limit_c": 0}], retries=1).suite
    report = run_suite(suite)
    case = report.results[0]
    if damage == "number":
        case.attempts[0].number = 2
    elif damage == "missing":
        case.attempts.clear()
    elif damage == "early_pass":
        case.attempts[0].status = "passed"
    elif damage == "budget":
        case.attempts.append(case.attempts[-1])
    elif damage == "steps":
        case.attempts[0].steps.clear()
    else:
        case.status = "passed"
        report.passed, report.failed = 1, 0
    result = evaluate_qualification(report, QualificationPolicy(0, 10, True, True), expected=suite)
    assert not result.qualified
    assert result.metrics.incomplete_cases == 1
    assert "inconsistent_case_or_retry_evidence" in result.issues


def test_worker_errors_are_incomplete_not_skipped_or_failed_cases(monkeypatch):
    from hil_automation import orchestration

    plan = ExecutionPlan("worker", [entry("broken")], 2)
    def broken(suite):
        raise RuntimeError("worker stopped")
    monkeypatch.setattr(orchestration, "run_suite", broken)
    result = evaluate_qualification(run_plan(plan), QualificationPolicy(0, 10, True, True), expected=plan)
    assert not result.qualified and "worker_failure" in result.issues
    assert result.metrics.incomplete_cases == 1
    assert result.metrics.failed_cases == result.metrics.skipped_cases == 0
