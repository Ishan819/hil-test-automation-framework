import sys

import pytest

from hil_automation.native import NativeExecutionError, run_native_tests


def test_native_success_captures_both_streams(native_executable):
    binary = native_executable("import sys\nprint('passed')\nprint('diagnostic', file=sys.stderr)")
    result = run_native_tests(binary)
    assert result.exit_code == 0
    assert result.stdout == "passed\n"
    assert result.stderr == "diagnostic\n"
    assert result.executable == str(binary.resolve())
    assert result.duration_ms >= 0


def test_native_failure_preserves_exit_code_and_output(native_executable):
    binary = native_executable("import sys\nprint('assertion failed')\nsys.exit(7)")
    result = run_native_tests(binary)
    assert result.exit_code == 7
    assert result.stdout == "assertion failed\n"
    assert result.stderr == ""


def test_missing_binary_has_clear_error(tmp_path):
    with pytest.raises(NativeExecutionError, match="Native test executable not found"):
        run_native_tests(tmp_path / "missing")


def test_native_timeout(native_executable):
    binary = native_executable("import time\ntime.sleep(30)")
    with pytest.raises(NativeExecutionError, match="timed out after 0.05 seconds"):
        run_native_tests(binary, timeout=0.05)


@pytest.mark.parametrize("timeout", [0, -1, True, False, "1", None,
                                    float("nan"), float("inf"), -float("inf"), 10**1000])
def test_invalid_timeout_is_rejected_before_execution(tmp_path, timeout):
    with pytest.raises(ValueError, match="finite positive number"):
        run_native_tests(tmp_path / "missing", timeout=timeout)


def test_nonexecutable_file_has_clear_error(tmp_path):
    binary = tmp_path / "not-executable"
    binary.write_text("not executable", encoding="utf-8")
    with pytest.raises(NativeExecutionError, match="Cannot execute native test binary"):
        run_native_tests(binary)


def test_directory_is_not_an_executable(tmp_path):
    with pytest.raises(NativeExecutionError, match="Cannot execute native test binary"):
        run_native_tests(tmp_path)


def test_relative_binary_is_resolved(native_executable, monkeypatch):
    binary = native_executable("print('relative')")
    monkeypatch.chdir(binary.parent)
    assert run_native_tests(binary.name).stdout == "relative\n"


def test_shell_metacharacters_are_literal(native_executable, tmp_path):
    marker = tmp_path / "must-not-exist"
    binary = native_executable("import sys\nprint(sys.argv[1])", name="native; echo injected")
    argument = f"; touch {marker}"
    result = run_native_tests(binary, arguments=(argument,))
    assert result.exit_code == 0
    assert result.stdout == f"{argument}\n"
    assert not marker.exists()


def test_native_duration_uses_monotonic_clock(monkeypatch):
    from hil_automation import native

    ticks = iter([10, 10.125])
    monkeypatch.setattr(native, "perf_counter", lambda: next(ticks))
    result = run_native_tests(sys.executable, arguments=("-c", "pass"))
    assert result.duration_ms == 125


def test_non_utf8_output_is_captured_without_crashing(native_executable):
    binary = native_executable("import os\nos.write(1, b'\\xff')\nos.write(2, b'\\xfe')")
    result = run_native_tests(binary)
    assert result.stdout == result.stderr == "\ufffd"


def test_google_xml_capture_uses_a_unique_temporary_path(native_executable):
    binary = native_executable("""import pathlib, sys
output = pathlib.Path(next(arg.split("xml:", 1)[1] for arg in sys.argv if arg.startswith("--gtest_output=")))
output.write_text('<testsuite name="Native"><testcase name="Works" time="0.01"/></testsuite>')
print(output)
""")
    first = run_native_tests(binary, capture_xml=True)
    second = run_native_tests(binary, capture_xml=True)
    from pathlib import Path

    assert first.results_captured is True
    assert first.cases[0].name == "Works"
    assert first.cases[0].duration_ms == 10
    assert first.stdout != second.stdout
    assert not Path(first.stdout.strip()).parent.exists()
    assert not Path(second.stdout.strip()).parent.exists()
    assert first.started_at <= first.finished_at


def test_capture_rejects_overriding_xml_destination(tmp_path):
    with pytest.raises(ValueError, match="manages --gtest_output"):
        run_native_tests(tmp_path / "missing", capture_xml=True,
                         arguments=("--gtest_output=xml:elsewhere.xml",))
