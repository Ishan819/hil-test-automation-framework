from pathlib import Path
import subprocess
import sys

import pytest

from hil_automation.protobuf import parse_result


ROOT = Path(__file__).resolve().parents[1]


def cli(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "hil_automation.cli", *map(str, args)],
        capture_output=True, text=True, cwd=cwd,
    )


@pytest.mark.parametrize("scenario, passed, failed, code", [
    ("smoke", 3, 0, 0), ("recovery", 3, 0, 0), ("faults", 0, 2, 1), ("failure_demo", 0, 2, 1),
])
def test_yaml_protobuf_reports_have_actual_results(tmp_path, scenario, passed, failed, code):
    output = tmp_path / f"{scenario}.pb"
    finished = cli(ROOT / "scenarios" / f"{scenario}.yaml", "--report-format", "protobuf", "--report", output)
    assert finished.returncode == code, finished.stderr
    result = parse_result(output.read_bytes())
    assert (result.summary.passed, result.summary.failed) == (passed, failed)
    assert result.summary.total == passed + failed
    assert f"Protobuf report: {output}" in finished.stdout


def test_default_binary_path_and_selected_case(tmp_path):
    finished = cli(
        ROOT / "scenarios/smoke.yaml", "--report-format", "protobuf",
        "--case", "device_responds_to_heartbeat", cwd=tmp_path,
    )
    assert finished.returncode == 0, finished.stderr
    result = parse_result((tmp_path / "reports/latest.pb").read_bytes())
    assert [case.name for case in result.cases] == ["device_responds_to_heartbeat"]


def test_listing_does_not_write_protobuf_report(tmp_path):
    output = tmp_path / "unused.pb"
    finished = cli(ROOT / "scenarios/smoke.yaml", "--list-tests", "--report-format", "protobuf", "--report", output)
    assert finished.returncode == 0
    assert not output.exists()


def test_native_protobuf_report_preserves_failure_exit_code(gtest_executable, tmp_path):
    binary = gtest_executable(
        '<testsuite name="Native"><testcase name="Bad" time="0.1"><failure message="bad"/></testcase></testsuite>',
        exit_code=1,
    )
    output = tmp_path / "native.pb"
    finished = cli("--native-tests", binary, "--report-format", "protobuf", "--report", output, "--quiet")
    assert finished.returncode == 1, finished.stderr
    result = parse_result(output.read_bytes())
    assert result.native_exit_code == 1
    assert result.cases[0].name == "Bad"
    assert result.cases[0].details == "bad"


def test_binary_output_cannot_overwrite_yaml_input(tmp_path):
    config = tmp_path / "suite.yaml"
    original = "suite: protected\nbench: {type: simulated}\ntests:\n  - name: alive\n    steps: [{action: expect_heartbeat}]\n"
    config.write_text(original)
    finished = cli(config, "--report-format", "protobuf", "--report", config)
    assert finished.returncode == 2
    assert "unrelated or invalid" in finished.stderr
    assert config.read_text() == original


def test_native_yaml_selection_conflict_and_unknown_format_remain_errors(tmp_path):
    for args in [
        ["--native-tests", str(tmp_path / "missing"), "--case", "case", "--report-format", "protobuf"],
        [str(ROOT / "scenarios/smoke.yaml"), "--report-format", "invalid"],
    ]:
        finished = cli(*args)
        assert finished.returncode == 2
        assert "Traceback" not in finished.stderr
