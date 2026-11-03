import json
from datetime import datetime

import pytest

from hil_automation.orchestration import run_plan
from hil_automation.plans import ExecutionPlan
from hil_automation.qualification import evaluate_qualification
from hil_automation.qualification_policy import QualificationPolicy
from hil_automation.reporting import ReportError, write_qualification_report
from test_parallel import entry


def test_qualification_json_contains_decision_criteria_metrics_and_execution_ids(tmp_path):
    plan = ExecutionPlan("release", [entry("healthy"), entry("fault", [
        {"action": "expect_temperature_below", "limit_c": 0},
    ], retries=1)], 2)
    batch = run_plan(plan)
    result = evaluate_qualification(batch, QualificationPolicy(), expected=plan)
    path = tmp_path / "qualification.json"
    write_qualification_report(result, path)
    data = json.loads(path.read_text())
    assert data == result.to_dict()
    assert data["decision"] == "not_qualified" and data["qualified"] is False
    assert data["complete_evidence"] is True
    assert data["policy"]["min_pass_percentage"] == 100
    assert data["observed"] == {
        "total_cases": 2, "passed_cases": 1, "failed_cases": 1,
        "skipped_cases": 0, "recovered_cases": 0, "incomplete_cases": 0, "pass_percentage": 50,
    }
    assert len(data["criteria"]) == 5 and len(data["failure_reasons"]) == 2
    references = data["execution_references"]
    assert [item["run_id"] for item in references] == [batch.run_id, *(suite.report.run_id for suite in batch.suites)]
    assert [item["index"] for item in references] == [0, 1, 2]
    assert all(item["finished_at"] >= item["started_at"] for item in references)
    assert datetime.fromisoformat(data["evaluated_at"]).utcoffset() is not None


def test_success_report_has_no_failure_reasons(tmp_path):
    suite = entry("healthy").suite
    from hil_automation.runner import run_suite
    report = evaluate_qualification(run_suite(suite), QualificationPolicy(), expected=suite)
    write_qualification_report(report, tmp_path / "passed.json")
    assert report.to_dict()["qualified"]
    assert report.to_dict()["failure_reasons"] == []
    assert all(item["reason"] is None for item in report.to_dict()["criteria"])


def test_report_omits_free_text_diagnostics_names_paths_and_environment(tmp_path, monkeypatch):
    from hil_automation import orchestration

    secret = "/Users/private/person/token=secret-value"
    plan = ExecutionPlan(secret, [entry(secret)], 2)
    def fail(suite):
        raise RuntimeError(secret)
    monkeypatch.setattr(orchestration, "run_suite", fail)
    batch = run_plan(plan)
    batch.run_id = secret
    result = evaluate_qualification(batch, QualificationPolicy(), expected=plan)
    path = tmp_path / "private.json"
    write_qualification_report(result, path)
    text = path.read_text()
    assert secret not in text
    assert "python_version" not in text and "machine" not in text
    assert not json.loads(text)["qualified"]
    assert "worker_failure" in json.loads(text)["evidence_issues"]


def test_atomic_write_failure_preserves_previous_qualification_report(tmp_path, monkeypatch):
    from hil_automation import reporting
    from hil_automation.runner import run_suite

    suite = entry("healthy").suite
    result = evaluate_qualification(run_suite(suite), QualificationPolicy(), expected=suite)
    path = tmp_path / "qualification.json"
    path.write_text("previous")
    def fail(*args):
        raise OSError("disk failure")
    monkeypatch.setattr(reporting.os, "replace", fail)
    with pytest.raises(ReportError, match="Cannot write qualification report"):
        write_qualification_report(result, path)
    assert path.read_text() == "previous"
    assert list(tmp_path.iterdir()) == [path]
