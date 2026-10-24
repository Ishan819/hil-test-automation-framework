from hil_automation.config import Suite, TestCase as HilTestCase
from hil_automation.runner import run_suite


def test_versioned_report_preserves_original_fields():
    report = run_suite(Suite("schema", {}, [
        HilTestCase("healthy", [{"action": "expect_heartbeat"}]),
    ])).to_dict()
    assert report["schema_version"] == "1.0"
    assert {"suite", "started_at", "passed", "failed", "results"} <= report.keys()
    assert report["results"][0]["details"] == "All steps passed"


def test_metadata_contains_only_allowlisted_runtime_information(monkeypatch):
    import platform

    monkeypatch.setenv("HIL_SECRET", "do-not-include")
    data = run_suite(Suite("metadata", {}, [])).to_dict()
    assert data["metadata"] == {
        "python_version": platform.python_version(),
        "system": platform.system(),
        "machine": platform.machine(),
        "started_at": data["started_at"],
        "finished_at": data["finished_at"],
    }
    assert "do-not-include" not in str(data)


def test_statistics_count_failed_and_skipped_steps():
    report = run_suite(Suite("stats", {}, [
        HilTestCase("fault", [
            {"action": "set_connection", "connected": False},
            {"action": "expect_heartbeat"}, {"action": "expect_heartbeat"},
        ]),
        HilTestCase("healthy", [{"action": "expect_heartbeat"}]),
    ]))
    assert report.to_dict()["statistics"] == {
        "total_cases": 2, "passed_cases": 1, "failed_cases": 1, "skipped_cases": 0,
        "duration_ms": report.duration_ms, "total_steps": 4, "executed_steps": 3,
        "passed_steps": 2, "failed_steps": 1, "skipped_steps": 1,
    }
    assert report.duration_ms >= sum(case.duration_ms for case in report.results) - 0.01


def test_failure_categories_follow_exception_types():
    suite = Suite("categories", {}, [
        HilTestCase("connection", [
            {"action": "set_connection", "connected": False}, {"action": "expect_heartbeat"},
        ]),
        HilTestCase("assertion", [{"action": "expect_temperature_below", "limit_c": 10}]),
        HilTestCase("invalid", [{"action": "unsupported"}]),
        HilTestCase("healthy", [{"action": "expect_heartbeat"}]),
    ])
    report = run_suite(suite)
    assert [case.failure_category for case in report.results] == [
        "simulated_connection_failure", "assertion_failure", "invalid_test_configuration", None,
    ]
    for case in report.results:
        assert case.steps[-1].failure_category == case.failure_category


def test_action_statistics_exclude_unexecuted_steps():
    report = run_suite(Suite("actions", {}, [
        HilTestCase("fault", [
            {"action": "expect_heartbeat"},
            {"action": "set_connection", "connected": False},
            {"action": "expect_heartbeat"}, {"action": "set_voltage", "value": 5},
        ]),
    ])).to_dict()
    assert report["action_statistics"] == {
        "expect_heartbeat": {"executed": 2, "passed": 1, "failed": 1},
        "set_connection": {"executed": 1, "passed": 1, "failed": 0},
    }
    assert sum(item["executed"] for item in report["action_statistics"].values()) == (
        report["statistics"]["executed_steps"]
    )


def test_atomic_json_replacement_and_cleanup(tmp_path, monkeypatch):
    import json
    import os
    import pytest
    from hil_automation import reporting

    destination = tmp_path / "report.json"
    destination.write_text("previous", encoding="utf-8")
    report = run_suite(Suite("atomic", {}, []))
    replace = os.replace

    def verify_replace(source, target):
        assert destination.read_text() == "previous"
        assert source.parent == destination.parent
        assert json.loads(source.read_text())["suite"] == "atomic"
        replace(source, target)

    monkeypatch.setattr(reporting.os, "replace", verify_replace)
    reporting.write_json_report(report, destination)
    assert json.loads(destination.read_text())["suite"] == "atomic"
    assert list(tmp_path.iterdir()) == [destination]

    def failed_replace(source, target):
        raise PermissionError("replacement denied")

    monkeypatch.setattr(reporting.os, "replace", failed_replace)
    original = destination.read_text()
    with pytest.raises(PermissionError, match="replacement denied"):
        reporting.write_json_report(report, destination)
    assert destination.read_text() == original
    assert list(tmp_path.iterdir()) == [destination]
