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


def test_junit_distinguishes_configuration_errors_and_skipped_cases(tmp_path):
    output = tmp_path / "fast.xml"
    report = run_suite(Suite("fast", {}, [
        HilTestCase("invalid", [{"action": "unknown"}]),
        HilTestCase("later", [{"action": "expect_heartbeat"}]),
    ]), fail_fast=True)
    write_junit_report(report, output)
    root = ET.parse(output).getroot()
    assert (root.get("errors"), root.get("failures"), root.get("skipped")) == ("1", "0", "1")
    assert root.find("testcase/error").get("type") == "invalid_test_configuration"
    assert root.findall("testcase")[1].find("skipped") is not None
    assert root.findall("testcase")[1].get("time") == "0.000000"


def test_junit_escapes_names_and_diagnostics_and_replaces_invalid_xml_characters(tmp_path):
    from hil_automation.runner import CaseResult

    report = run_suite(Suite('suite <&" é', {}, []))
    report.results = [CaseResult('case <&"\x00', "failed", 1234.5, 'actual < expected & "bad"\x01')]
    report.failed = 1
    output = tmp_path / "escaped.xml"
    write_junit_report(report, output)
    root = ET.parse(output).getroot()
    assert root.get("name") == 'suite <&" é'
    case = root.find("testcase")
    assert case.get("name") == 'case <&"\ufffd'
    assert case.get("time") == "1.234500"
    assert case.find("failure").text == 'actual < expected & "bad"\ufffd'
    assert case.find("failure").get("message") == case.find("failure").text


def test_junit_empty_and_single_case_reports(tmp_path):
    for count in (0, 1):
        suite = Suite("selection", {}, [
            HilTestCase("selected", [{"action": "expect_heartbeat"}]),
        ][:count])
        output = tmp_path / f"{count}.xml"
        write_junit_report(run_suite(suite), output)
        root = ET.parse(output).getroot()
        assert root.get("tests") == str(count)
        assert len(root.findall("testcase")) == count
        assert root.get("failures") == root.get("errors") == root.get("skipped") == "0"


def test_junit_write_failure_preserves_old_report_and_cleans_temporary(tmp_path, monkeypatch):
    import pytest
    from hil_automation import reporting

    output = tmp_path / "report.xml"
    output.write_text("previous", encoding="utf-8")

    def denied(source, destination):
        raise PermissionError("replacement denied")

    monkeypatch.setattr(reporting.os, "replace", denied)
    with pytest.raises(reporting.ReportError, match="Cannot write JUnit XML report"):
        write_junit_report(run_suite(Suite("denied", {}, [])), output)
    assert output.read_text() == "previous"
    assert list(tmp_path.iterdir()) == [output]
