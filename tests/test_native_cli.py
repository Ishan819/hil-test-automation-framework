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
    ["--report", "unused.json"], ["--report-format", "json"], ["--report-format", "junit"],
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
