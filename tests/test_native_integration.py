import json
import subprocess
import sys
from xml.etree import ElementTree as ET

import pytest

from hil_automation.native import run_native_tests


pytestmark = pytest.mark.native_integration


def run_cli(binary, *arguments, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "hil_automation.cli", "--native-tests", str(binary),
         *map(str, arguments)], cwd=cwd, capture_output=True, text=True,
    )


def test_real_gtest_xml_capture(compiled_gtest_binary):
    result = run_native_tests(compiled_gtest_binary, capture_xml=True)
    assert result.successful
    assert len(result.cases) == 10
    assert all(case.suite == "SimulatedBenchTest" for case in result.cases)
    assert all(case.status == "passed" for case in result.cases)
    assert all(case.duration_ms >= 0 for case in result.cases)
    assert "[  PASSED  ] 10 tests." in result.stdout


def test_real_native_json_cli(compiled_gtest_binary, tmp_path):
    output = tmp_path / "native.json"
    finished = run_cli(compiled_gtest_binary, "--report", output, "--quiet")
    assert finished.returncode == 0, finished.stderr
    assert finished.stdout == "Native results: 10 passed, 0 failed, 0 skipped\n"
    data = json.loads(output.read_text())
    assert data["schema_version"] == "1.0"
    assert data["native_exit_code"] == 0
    assert data["passed"] == data["statistics"]["total_cases"] == len(data["native_results"]) == 10
    assert data["results"] == []
    assert data["run_id"]


def test_real_native_junit_cli(compiled_gtest_binary, tmp_path):
    output = tmp_path / "native.xml"
    finished = run_cli(compiled_gtest_binary, "--report-format", "junit", "--report", output)
    assert finished.returncode == 0, finished.stderr
    root = ET.parse(output).getroot()
    assert root.get("tests") == "10"
    assert root.get("failures") == root.get("errors") == root.get("skipped") == "0"
    assert len(root.findall("testcase")) == 10
    assert all(case.get("classname") == "SimulatedBenchTest" for case in root.findall("testcase"))


def test_real_mixed_outcomes_capture(compiled_reporting_binary):
    result = run_native_tests(compiled_reporting_binary, capture_xml=True)
    assert result.exit_code == 1
    assert result.result_error is None
    assert not result.successful
    assert [case.status for case in result.cases] == ["passed", "failed", "skipped", "disabled"]
    assert "expected < 5 & safe" in result.cases[1].details
    assert "Intentional integration skip" in result.cases[2].details


@pytest.mark.parametrize("report_format", ["json", "junit"])
def test_real_failing_native_reports(compiled_reporting_binary, tmp_path, report_format):
    output = tmp_path / f"native.{report_format}"
    finished = run_cli(
        compiled_reporting_binary, "--report-format", report_format, "--report", output,
        "--native-results",
    )
    assert finished.returncode == 1, finished.stderr
    assert "1 passed, 1 failed, 2 skipped" in finished.stdout
    if report_format == "json":
        data = json.loads(output.read_text())
        assert (data["passed"], data["failed"], data["skipped"]) == (1, 1, 2)
        assert data["statistics"]["total_cases"] == 4
        assert len(data["native_results"]) == 4
        assert "expected < 5 & safe" in data["native_results"][1]["details"]
    else:
        root = ET.parse(output).getroot()
        assert (root.get("tests"), root.get("failures"), root.get("skipped")) == ("4", "1", "2")
        failure = root.find("testcase/failure")
        assert "expected < 5 & safe" in failure.text


@pytest.mark.parametrize("report_format, suffix", [("json", "json"), ("junit", "xml")])
def test_native_default_report_paths(compiled_gtest_binary, tmp_path, report_format, suffix):
    finished = run_cli(compiled_gtest_binary, "--report-format", report_format, cwd=tmp_path)
    assert finished.returncode == 0, finished.stderr
    assert (tmp_path / "reports" / f"latest.{suffix}").is_file()


def test_real_structured_native_display(compiled_gtest_binary, tmp_path):
    finished = run_cli(compiled_gtest_binary, "--native-results", "--verbose", cwd=tmp_path)
    assert finished.returncode == 0, finished.stderr
    assert "SimulatedBenchTest.StartsWithSafeDefaults" in finished.stdout
    assert "ms)" in finished.stdout
    assert not (tmp_path / "reports").exists()


@pytest.mark.parametrize("pattern, expected", [
    ("SimulatedBenchTest.StartsWithSafeDefaults", 1), ("NoSuchSuite.*", 0),
])
def test_real_filtered_and_empty_gtest_results(compiled_gtest_binary, pattern, expected):
    result = run_native_tests(
        compiled_gtest_binary, capture_xml=True, arguments=(f"--gtest_filter={pattern}",),
    )
    assert result.successful
    assert len(result.cases) == expected


@pytest.mark.parametrize("pattern, expected_names", [
    ("SimulatedBenchTest.StartsWithSafeDefaults", ["StartsWithSafeDefaults"]),
    ("SimulatedBenchTest.Accepts*", [
        "AcceptsVoltageIncludingBoundaries", "AcceptsTemperatureIncludingBoundaries",
    ]),
    ("SimulatedBenchTest.StartsWithSafeDefaults:SimulatedBenchTest.CanDisconnectAndReconnect", [
        "StartsWithSafeDefaults", "CanDisconnectAndReconnect",
    ]),
    ("SimulatedBenchTest.Accepts*-*.AcceptsTemperature*", ["AcceptsVoltageIncludingBoundaries"]),
])
@pytest.mark.parametrize("report_format", ["json", "junit"])
def test_filtered_native_reports_only_contain_selected_cases(
    compiled_gtest_binary, tmp_path, pattern, expected_names, report_format,
):
    output = tmp_path / f"filtered.{report_format}"
    finished = run_cli(
        compiled_gtest_binary, "--native-filter", pattern, "--report-format", report_format,
        "--report", output, "--quiet",
    )
    assert finished.returncode == 0, finished.stderr
    assert finished.stdout == f"Native results: {len(expected_names)} passed, 0 failed, 0 skipped\n"
    if report_format == "json":
        data = json.loads(output.read_text())
        assert [case["name"] for case in data["native_results"]] == expected_names
        assert data["passed"] == data["statistics"]["total_cases"] == len(expected_names)
        assert data["native_exit_code"] == data["failed"] == data["skipped"] == 0
        assert data["results"] == []
    else:
        root = ET.parse(output).getroot()
        assert [case.get("name") for case in root.findall("testcase")] == expected_names
        assert root.get("tests") == str(len(expected_names))
        assert root.get("failures") == root.get("errors") == root.get("skipped") == "0"


@pytest.mark.parametrize("pattern, names, expected_code", [
    ("ReportingFixture.Passing", ["Passing"], 0),
    ("ReportingFixture.Failing", ["Failing"], 1),
    ("ReportingFixture.Passing:ReportingFixture.Failing", ["Passing", "Failing"], 1),
])
@pytest.mark.parametrize("report_format", ["json", "junit"])
def test_filtering_excludes_unselected_faults_and_preserves_failure_exit_codes(
    compiled_reporting_binary, tmp_path, pattern, names, expected_code, report_format,
):
    output = tmp_path / f"selected.{report_format}"
    finished = run_cli(
        compiled_reporting_binary, "--native-filter", pattern, "--report-format", report_format,
        "--report", output,
    )
    assert finished.returncode == expected_code, finished.stderr
    if report_format == "json":
        data = json.loads(output.read_text())
        assert [case["name"] for case in data["native_results"]] == names
        assert data["native_exit_code"] == expected_code
        assert data["failed"] == expected_code
        assert data["skipped"] == 0
        if expected_code:
            assert "Intentional reporting fixture failure" in data["native_results"][-1]["details"]
    else:
        root = ET.parse(output).getroot()
        assert [case.get("name") for case in root.findall("testcase")] == names
        assert root.get("failures") == str(expected_code)
        assert root.get("skipped") == "0"


@pytest.mark.parametrize("report_format", ["json", "junit"])
def test_real_filter_with_no_matches_preserves_report_and_returns_error(
    compiled_gtest_binary, tmp_path, report_format,
):
    output = tmp_path / f"previous.{report_format}"
    output.write_text("previous report", encoding="utf-8")
    finished = run_cli(
        compiled_gtest_binary, "--native-filter", "MissingSuite.*",
        "--report-format", report_format, "--report", output, "--quiet",
    )
    assert finished.returncode == 2
    assert "Native filter matched no tests" in finished.stderr
    assert "passed" not in finished.stdout
    assert output.read_text() == "previous report"


def test_real_filter_without_report_still_detects_zero_matches(compiled_gtest_binary, tmp_path):
    finished = run_cli(compiled_gtest_binary, "--native-filter", "MissingSuite.*", cwd=tmp_path)
    assert finished.returncode == 2
    assert "matched no tests" in finished.stderr
    assert "passed" not in finished.stdout
    assert not (tmp_path / "reports").exists()
