from hil_automation.config import Suite, TestCase as HilTestCase
from hil_automation.runner import run_suite


def test_versioned_report_preserves_original_fields():
    report = run_suite(Suite("schema", {}, [
        HilTestCase("healthy", [{"action": "expect_heartbeat"}]),
    ])).to_dict()
    assert report["schema_version"] == "1.0"
    assert {"suite", "started_at", "passed", "failed", "results"} <= report.keys()
    assert report["results"][0]["details"] == "All steps passed"
