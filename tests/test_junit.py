from xml.etree import ElementTree as ET

from hil_automation.config import Suite, TestCase as HilTestCase
from hil_automation.reporting import write_junit_report
from hil_automation.runner import run_suite


def test_junit_report_has_passing_and_failing_testcases(tmp_path):
    report = run_suite(Suite("junit", {}, [
        HilTestCase("healthy", [{"action": "expect_heartbeat"}]),
        HilTestCase("hot", [{"action": "expect_temperature_below", "limit_c": 0}]),
    ]))
    output = tmp_path / "nested" / "report.xml"
    write_junit_report(report, output)
    root = ET.parse(output).getroot()
    assert root.tag == "testsuite"
    assert (root.get("tests"), root.get("failures"), root.get("errors")) == ("2", "1", "0")
    assert root.find("testcase/failure").get("type") == "assertion_failure"
    assert [case.get("name") for case in root.findall("testcase")] == ["healthy", "hot"]
    assert float(root.get("time")) == report.duration_ms / 1000
    assert root.get("timestamp") == report.started_at
