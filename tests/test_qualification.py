from copy import deepcopy

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
