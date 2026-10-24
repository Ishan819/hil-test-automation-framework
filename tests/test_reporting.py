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
