"""Compare shared report semantics while respecting format-specific fields."""
import json
from xml.etree import ElementTree as ET

import pytest

from hil_automation.config import Suite, TestCase as HilTestCase
from hil_automation.native import run_native_tests
from hil_automation.protobuf import parse_result
from hil_automation.reporting import native_report, write_json_report, write_junit_report, write_protobuf_report
from hil_automation.runner import run_suite


def compare(report, tmp_path):
    write_json_report(report, tmp_path / "result.json")
    write_junit_report(report, tmp_path / "result.xml")
    write_protobuf_report(report, tmp_path / "result.pb")
    data = json.loads((tmp_path / "result.json").read_text())
    xml = ET.parse(tmp_path / "result.xml").getroot()
    binary = parse_result((tmp_path / "result.pb").read_bytes())
    assert data["run_id"] == xml.get("id") == binary.run_id
    assert data["suite"] == xml.get("name") == binary.suite
    assert data["passed"] == binary.summary.passed
    assert data["failed"] == binary.summary.failed == int(xml.get("failures")) + int(xml.get("errors"))
    assert data["skipped"] == binary.summary.skipped == int(xml.get("skipped"))
    assert data["statistics"]["total_cases"] == binary.summary.total == int(xml.get("tests"))
    assert data["duration_ms"] == binary.summary.duration_ms
    assert float(xml.get("time")) * 1000 == pytest.approx(report.duration_ms, abs=0.0005)
    cases = [(report.suite, c) for c in report.results] + [(c.suite, c) for c in report.native_results]
    for (suite, case), node, message in zip(cases, xml.findall("testcase"), binary.cases, strict=True):
        assert suite == node.get("classname") == message.suite
        assert case.name == node.get("name") == message.name
        assert case.duration_ms == message.duration_ms
        assert float(node.get("time")) * 1000 == pytest.approx(case.duration_ms, abs=0.0005)
        assert (node.find("failure") is not None or node.find("error") is not None) == (case.status == "failed")
        assert (node.find("skipped") is not None) == (case.status in ("skipped", "disabled"))
        assert message.status == {"passed": 1, "failed": 2, "skipped": 3, "disabled": 4}[case.status]
    return data, xml, binary


def test_retry_fail_fast_and_skips_match_across_formats(tmp_path):
    report = run_suite(Suite("formats", {}, [
        HilTestCase("healthy", [{"action": "expect_heartbeat"}]),
        HilTestCase("retry", [{"action": "expect_temperature_below", "limit_c": 0}], retries=2),
        HilTestCase("unexecuted", [{"action": "expect_heartbeat"}]),
    ]), fail_fast=True)
    data, xml, binary = compare(report, tmp_path)
    history = json.loads(binary.cases[1].details.split("\nRetry history: ", 1)[1])
    assert history == json.loads(xml.findall("testcase")[1].find("system-out").text)
    assert history["attempts"] == data["results"][1]["attempts"]
    assert history["retry_count"] == 2


@pytest.mark.native_integration
def test_real_google_test_outcomes_match_across_formats(compiled_reporting_binary, tmp_path):
    result = run_native_tests(compiled_reporting_binary, capture_xml=True)
    report = native_report(result)
    data, _, binary = compare(report, tmp_path)
    assert binary.native_exit_code == result.exit_code != 0
    assert {c["status"] for c in data["native_results"]} >= {"passed", "failed", "skipped", "disabled"}
