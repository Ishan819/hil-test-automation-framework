import json

from hil_automation.native import run_native_tests
from hil_automation.reporting import native_report, write_json_report


def test_native_cases_extend_json_without_changing_python_results(gtest_executable, tmp_path):
    binary = gtest_executable("""<testsuite name="Voltage">
      <testcase name="Nominal" time="0.002"/>
    </testsuite>""")
    result = run_native_tests(binary, capture_xml=True)
    report = native_report(result)
    path = tmp_path / "native.json"
    write_json_report(report, path)
    data = json.loads(path.read_text())
    assert data["schema_version"] == "1.0"
    assert data["results"] == []
    assert data["native_results"] == [{
        "suite": "Voltage", "name": "Nominal", "status": "passed", "duration_ms": 2,
        "details": "",
    }]
    assert (data["passed"], data["failed"], data["native_exit_code"]) == (1, 0, 0)
    assert data["statistics"]["total_cases"] == 1


def test_native_failure_skip_and_disabled_counts_and_serialization(gtest_executable, tmp_path):
    binary = gtest_executable("""<testsuite name="Mixed" tests="4" failures="1" skipped="1" disabled="1">
      <testcase name="Pass" time="0.001"/>
      <testcase name="Fail" time="0.0125"><failure message="expected &lt; 5">trace.cpp:9</failure></testcase>
      <testcase name="Skip" result="skipped"><skipped message="not ready"/></testcase>
      <testcase name="DISABLED_Later" status="notrun" result="suppressed"/>
    </testsuite>""", exit_code=1)
    result = run_native_tests(binary, capture_xml=True)
    report = native_report(result)
    path = tmp_path / "mixed.json"
    write_json_report(report, path)
    data = json.loads(path.read_text())
    assert (data["passed"], data["failed"], data["skipped"]) == (1, 1, 2)
    assert data["native_exit_code"] == 1
    assert data["statistics"]["total_cases"] == 4
    assert data["statistics"]["skipped_cases"] == 2
    assert data["duration_ms"] == result.duration_ms
    assert data["native_results"][1]["duration_ms"] == 12.5
    assert data["native_results"][1]["details"] == "expected < 5\ntrace.cpp:9"
    assert data["action_statistics"] == {}
    assert data["statistics"]["total_steps"] == 0
    assert data["metadata"]["started_at"] == result.started_at
    assert data["metadata"]["finished_at"] == result.finished_at


def test_python_and_native_structures_can_coexist_without_fake_steps():
    from dataclasses import replace
    from hil_automation.config import Suite, TestCase as HilTestCase
    from hil_automation.native_results import NativeCaseResult
    from hil_automation.runner import run_suite

    python_report = run_suite(Suite("mixed", {}, [
        HilTestCase("python-case", [{"action": "expect_heartbeat"}]),
    ]))
    mixed = replace(
        python_report, passed=2, failed=1, skipped=1, native_exit_code=1,
        native_results=[
            NativeCaseResult("Native", "Pass", "passed", 1),
            NativeCaseResult("Native", "Fail", "failed", 2, "assertion failed"),
            NativeCaseResult("Native", "Skip", "skipped", 0, "not ready"),
        ],
    ).to_dict()
    assert mixed["statistics"]["total_cases"] == 4
    assert (mixed["statistics"]["passed_cases"], mixed["statistics"]["failed_cases"]) == (2, 1)
    assert mixed["statistics"]["skipped_cases"] == 1
    assert mixed["statistics"]["executed_steps"] == 1
    assert len(mixed["results"]) == 1
    assert mixed["results"][0]["steps"][0]["action"] == "expect_heartbeat"
    assert len(mixed["native_results"]) == 3
    assert "steps" not in mixed["native_results"][0]


def test_incomplete_or_uncaptured_native_results_cannot_be_reported(gtest_executable):
    import pytest
    from hil_automation.native import NativeResult
    from hil_automation.reporting import ReportError

    with pytest.raises(ReportError, match="capture is required"):
        native_report(NativeResult("binary", 0, "", "", 1))
    invalid = run_native_tests(gtest_executable(None), capture_xml=True)
    with pytest.raises(ReportError, match="incomplete native results"):
        native_report(invalid)


def test_empty_native_capture_has_zero_case_counts(gtest_executable):
    result = run_native_tests(gtest_executable('<testsuites tests="0"/>'), capture_xml=True)
    data = native_report(result).to_dict()
    assert (data["passed"], data["failed"], data["skipped"]) == (0, 0, 0)
    assert data["statistics"]["total_cases"] == 0
    assert data["native_results"] == []


def test_native_junit_failures_skips_disabled_and_escaping(gtest_executable, tmp_path):
    from xml.etree import ElementTree as ET
    from hil_automation.reporting import write_junit_report

    binary = gtest_executable("""<testsuite name="Native &amp; Suite">
      <testcase name="Pass &lt; value" time="0.002"/>
      <testcase name="Fail" time="0.0125"><failure message="expected &lt; 5 &amp; safe"/></testcase>
      <testcase name="Skip" result="skipped"><skipped message="not ready"/></testcase>
      <testcase name="DISABLED_Later" status="notrun"/>
    </testsuite>""", exit_code=1)
    report = native_report(run_native_tests(binary, capture_xml=True))
    path = tmp_path / "native.xml"
    write_junit_report(report, path)
    root = ET.parse(path).getroot()
    assert (root.get("tests"), root.get("failures"), root.get("skipped"), root.get("errors")) == (
        "4", "1", "2", "0",
    )
    cases = root.findall("testcase")
    assert cases[0].get("name") == "Pass < value"
    assert cases[0].get("classname") == "Native & Suite"
    assert cases[1].get("time") == "0.012500"
    assert cases[1].find("failure").get("type") == "native_test_failure"
    assert cases[1].find("failure").text == "expected < 5 & safe"
    assert cases[2].find("skipped").get("message") == "not ready"
    assert cases[3].find("skipped").get("message") == "Disabled in GoogleTest"


def test_mixed_junit_preserves_python_and_native_classnames(tmp_path):
    from xml.etree import ElementTree as ET
    from hil_automation.native_results import NativeCaseResult
    from hil_automation.reporting import write_junit_report
    from hil_automation.runner import CaseResult, RunReport

    report = RunReport(
        "python-suite", "", 1, 1,
        [CaseResult("python-case", "failed", 1, "invalid", failure_category="invalid_test_configuration")],
        native_results=[NativeCaseResult("cpp-suite", "cpp-case", "passed", 2)],
    )
    path = tmp_path / "mixed.xml"
    write_junit_report(report, path)
    root = ET.parse(path).getroot()
    assert (root.get("tests"), root.get("errors"), root.get("failures")) == ("2", "1", "0")
    assert [case.get("classname") for case in root.findall("testcase")] == ["python-suite", "cpp-suite"]
