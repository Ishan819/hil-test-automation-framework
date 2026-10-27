import subprocess
import sys

import pytest


def cli(*arguments):
    return subprocess.run(
        [sys.executable, "-m", "hil_automation.cli", *map(str, arguments)],
        capture_output=True, text=True,
    )


def test_cli_executes_native_binary_without_yaml(native_executable, tmp_path, monkeypatch):
    binary = native_executable("print('native passed')")
    monkeypatch.chdir(tmp_path)
    finished = cli("--native-tests", binary)
    assert finished.returncode == 0, finished.stderr
    assert finished.stdout == "native passed\nNative tests: passed (exit code 0)\n"
    assert finished.stderr == ""
    assert not (tmp_path / "reports").exists()


def test_cli_native_failure_preserves_output_and_returns_one(native_executable):
    binary = native_executable("import sys\nprint('failed assertion')\nprint('diagnostic', file=sys.stderr)\nsys.exit(7)")
    finished = cli("--native-tests", binary)
    assert finished.returncode == 1
    assert finished.stdout == "failed assertion\nNative tests: failed (exit code 7)\n"
    assert finished.stderr == "diagnostic\n"


def test_cli_native_missing_binary_returns_two(tmp_path):
    finished = cli("--native-tests", tmp_path / "missing")
    assert finished.returncode == 2
    assert "Native test executable not found" in finished.stderr
    assert "Traceback" not in finished.stderr


def test_cli_native_timeout_returns_two(native_executable):
    binary = native_executable("import time\ntime.sleep(30)")
    finished = cli("--native-tests", binary, "--native-timeout", "0.05")
    assert finished.returncode == 2
    assert "timed out after 0.05 seconds" in finished.stderr


@pytest.mark.parametrize("timeout", ["0", "-1", "nan", "inf", "invalid"])
def test_cli_native_rejects_invalid_timeout(tmp_path, timeout):
    finished = cli("--native-tests", tmp_path / "missing", f"--native-timeout={timeout}")
    assert finished.returncode == 2
    assert "Traceback" not in finished.stderr


@pytest.mark.parametrize("arguments", [
    ["suite.yaml"], ["--case", "case"], ["--list-tests"], ["--fail-fast"],
])
def test_native_rejects_yaml_only_options(tmp_path, arguments):
    finished = cli("--native-tests", tmp_path / "missing", *arguments)
    assert finished.returncode == 2
    assert "provide either" in finished.stderr or "cannot be combined" in finished.stderr
    assert "not found" not in finished.stderr


def test_native_timeout_requires_native_mode():
    finished = cli("suite.yaml", "--native-timeout", "1")
    assert finished.returncode == 2
    assert "--native-timeout requires --native-tests" in finished.stderr


def test_cli_requires_an_execution_source():
    finished = cli()
    assert finished.returncode == 2
    assert "provide a YAML config or --native-tests BINARY" in finished.stderr


def test_quiet_native_mode_keeps_summary_and_stderr(native_executable):
    binary = native_executable("import sys\nprint('detail')\nprint('diagnostic', file=sys.stderr)")
    finished = cli("--native-tests", binary, "--quiet")
    assert finished.returncode == 0
    assert finished.stdout == "Native tests: passed (exit code 0)\n"
    assert finished.stderr == "diagnostic\n"


def test_verbose_native_mode_shows_duration_and_executable(native_executable):
    binary = native_executable("print('detail')")
    finished = cli("--native-tests", binary, "--verbose")
    assert finished.returncode == 0
    assert f"Native executable: {binary.resolve()}" in finished.stdout
    assert "Native duration:" in finished.stdout
    assert "ms\ndetail" in finished.stdout


def test_native_results_display_individual_cases_without_writing_reports(gtest_executable, tmp_path, monkeypatch):
    binary = gtest_executable('<testsuite name="Native"><testcase name="Works" time="0.01"/></testsuite>')
    monkeypatch.chdir(tmp_path)
    finished = cli("--native-tests", binary, "--native-results", "--verbose")
    assert finished.returncode == 0, finished.stderr
    assert "Native.Works (10.000 ms)" in finished.stdout
    assert "Native results: 1 passed, 0 failed, 0 skipped" in finished.stdout
    assert not (tmp_path / "reports").exists()


def test_native_report_option_enables_capture(gtest_executable, tmp_path):
    import json

    binary = gtest_executable('<testsuite name="Native"><testcase name="Works" time="0.01"/></testsuite>')
    output = tmp_path / "native.json"
    finished = cli("--native-tests", binary, "--report", output)
    assert finished.returncode == 0, finished.stderr
    assert json.loads(output.read_text())["native_results"][0]["name"] == "Works"


def test_native_capture_error_preserves_existing_report(gtest_executable, tmp_path):
    output = tmp_path / "existing.json"
    output.write_text("previous")
    finished = cli("--native-tests", gtest_executable(None), "--report", output)
    assert finished.returncode == 2
    assert "Cannot read GoogleTest XML" in finished.stderr
    assert "passed" not in finished.stdout
    assert output.read_text() == "previous"


def test_native_results_requires_native_mode():
    finished = cli("suite.yaml", "--native-results")
    assert finished.returncode == 2
    assert "--native-results requires --native-tests" in finished.stderr


@pytest.mark.parametrize("xml, exit_code", [
    ('<testsuite name="S"><testcase name="T" time="0"><failure message="bad"/></testcase></testsuite>', 0),
    ('<testsuite name="S"><testcase name="T" time="0"/></testsuite>', 7),
    ('<testsuite name="S" tests="2"><testcase name="T" time="0"/></testsuite>', 0),
])
def test_cli_never_reports_inconsistent_capture_as_passing(gtest_executable, tmp_path, xml, exit_code):
    output = tmp_path / "previous.json"
    output.write_text("previous")
    finished = cli("--native-tests", gtest_executable(xml, exit_code), "--report", output)
    assert finished.returncode == 2
    assert "Error:" in finished.stderr
    assert "Native results:" not in finished.stdout
    assert output.read_text() == "previous"


def test_native_report_write_error_is_clear(gtest_executable, tmp_path):
    binary = gtest_executable('<testsuite name="S"><testcase name="T" time="0"/></testsuite>')
    finished = cli("--native-tests", binary, "--report", tmp_path)
    assert finished.returncode == 2
    assert "Cannot write JSON report" in finished.stderr
    assert "Native results:" not in finished.stdout


def test_native_filter_cli_forwards_pattern_and_shows_selected_outcome(native_executable):
    binary = native_executable("""import pathlib, sys
assert '--gtest_filter=Suite.One:Suite.Two-Suite.Excluded' in sys.argv
output = pathlib.Path(next(arg.split("xml:", 1)[1] for arg in sys.argv if arg.startswith("--gtest_output=")))
output.write_text('<testsuite name="Suite"><testcase name="One" time="0"/></testsuite>')
""")
    finished = cli(
        "--native-tests", binary, "--native-filter", "Suite.One:Suite.Two-Suite.Excluded", "--quiet",
    )
    assert finished.returncode == 0, finished.stderr
    assert finished.stdout == "Native results: 1 passed, 0 failed, 0 skipped\n"


@pytest.mark.parametrize("arguments", [[], ["suite.yaml"], ["suite.yaml", "--case", "one"]])
def test_cli_filter_requires_native_mode(arguments):
    finished = cli(*arguments, "--native-filter", "Suite.*")
    assert finished.returncode == 2
    assert "--native-filter requires --native-tests" in finished.stderr


@pytest.mark.parametrize("arguments", [["--case", "one"], ["--list-tests"], ["--fail-fast"], ["suite.yaml"]])
def test_cli_filter_rejects_yaml_selection_combinations(tmp_path, arguments):
    finished = cli("--native-tests", tmp_path / "missing", "--native-filter", "Suite.*", *arguments)
    assert finished.returncode == 2
    assert "cannot be combined" in finished.stderr or "provide either" in finished.stderr
    assert "not found" not in finished.stderr


@pytest.mark.parametrize("pattern", ["", "   ", "Suite.\nCase"])
def test_cli_filter_rejects_invalid_patterns(tmp_path, pattern):
    finished = cli("--native-tests", tmp_path / "missing", "--native-filter", pattern)
    assert finished.returncode == 2
    assert "Native filter must be a non-empty string" in finished.stderr
    assert "Traceback" not in finished.stderr


def test_cli_filter_no_matches_is_an_explicit_error(gtest_executable):
    finished = cli(
        "--native-tests", gtest_executable('<testsuites tests="0"/>'),
        "--native-filter", "Missing.*", "--quiet",
    )
    assert finished.returncode == 2
    assert "Native filter matched no tests" in finished.stderr
    assert "passed" not in finished.stdout
