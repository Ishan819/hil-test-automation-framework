import json
import subprocess
import sys
from xml.etree import ElementTree as ET

import pytest
import yaml

from hil_automation.protobuf import parse_result


@pytest.fixture
def suite(tmp_path):
    path = tmp_path / "tagged.yaml"
    path.write_text(yaml.safe_dump({
        "suite": "tag-selection", "bench": {"type": "simulated"}, "tests": [
            {"name": "voltage", "tags": ["smoke"], "steps": [{"action": "set_voltage", "value": 5}]},
            {"name": "heartbeat", "tags": ["smoke", "connection"], "steps": [{"action": "expect_heartbeat"}]},
            {"name": "thermal", "tags": ["thermal"], "steps": [{"action": "expect_temperature_below", "limit_c": 0}]},
        ],
    }))
    return path


@pytest.mark.parametrize("tag, names, code", [
    ("smoke", ["voltage", "heartbeat"], 0), ("connection", ["heartbeat"], 0),
    ("thermal", ["thermal"], 1),
])
@pytest.mark.parametrize("format_name", ["json", "junit", "protobuf"])
def test_tag_execution_reports_only_selected_cases(suite, tmp_path, tag, names, code, format_name):
    output = tmp_path / f"selected.{format_name}"
    finished = subprocess.run([
        sys.executable, "-m", "hil_automation.cli", str(suite), "--tag", tag,
        "--report-format", format_name, "--report", str(output),
    ], capture_output=True, text=True)
    assert finished.returncode == code, finished.stderr
    if format_name == "json":
        report = json.loads(output.read_text())
        assert [case["name"] for case in report["results"]] == names
        assert report["failed"] == code
    elif format_name == "junit":
        root = ET.parse(output).getroot()
        assert [case.get("name") for case in root.findall("testcase")] == names
        assert root.get("failures") == str(code)
    else:
        report = parse_result(output.read_bytes())
        assert [case.name for case in report.cases] == names
        assert report.summary.failed == code


@pytest.mark.parametrize("tag", ["missing", "", " smoke "])
def test_no_matching_tag_never_reports_success(suite, tmp_path, tag):
    output = tmp_path / "previous.json"
    output.write_text("previous")
    finished = subprocess.run([
        sys.executable, "-m", "hil_automation.cli", str(suite),
        "--tag", tag, "--report", str(output),
    ], capture_output=True, text=True)
    assert finished.returncode == 2
    assert "Error:" in finished.stderr
    assert "passed" not in finished.stdout
    assert output.read_text() == "previous"


@pytest.mark.parametrize("options", [
    ["--case", "heartbeat"], ["--list-tests"], ["--native-tests", "missing"],
])
def test_tag_conflicts_are_rejected(suite, options):
    finished = subprocess.run([
        sys.executable, "-m", "hil_automation.cli", str(suite), "--tag", "smoke", *options,
    ], capture_output=True, text=True)
    assert finished.returncode == 2
    assert "not allowed" in finished.stderr or "provide either" in finished.stderr
