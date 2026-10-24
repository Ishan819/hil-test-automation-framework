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
