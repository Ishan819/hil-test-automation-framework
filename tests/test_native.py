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


@pytest.mark.parametrize("xml, code, error", [
    (None, 0, "Cannot read GoogleTest XML"),
    ("<testsuites>", 0, "Cannot read GoogleTest XML"),
    ('<testsuite name="Suite" tests="2"><testcase name="One" time="0"/></testsuite>',
     0, "Incomplete GoogleTest XML"),
    ('<testsuite name="Suite"><testcase name="One" time="0"/></testsuite>',
     7, "exited with code 7 but XML reports no failures"),
    ('<testsuite name="Suite"><testcase name="One" time="0"><failure message="bad"/></testcase></testsuite>',
     0, "exited successfully but GoogleTest XML reports failures"),
    ('<testsuites/>', 0, "must declare tests=0"),
])
def test_capture_errors_can_never_report_success(gtest_executable, xml, code, error):
    result = run_native_tests(gtest_executable(xml, code), capture_xml=True)
    assert result.successful is False
    assert error in result.result_error
    assert result.exit_code == code
    assert result.stdout == "native output\n"
    assert result.stderr == "native diagnostic\n"


def test_valid_failure_is_an_outcome_not_a_capture_error(gtest_executable):
    binary = gtest_executable(
        '<testsuite name="Suite"><testcase name="One" time="0"><failure message="bad"/></testcase></testsuite>',
        exit_code=1,
    )
    result = run_native_tests(binary, capture_xml=True)
    assert result.result_error is None
    assert result.successful is False
    assert result.cases[0].status == "failed"


def test_unexpected_termination_is_never_successful(native_executable):
    binary = native_executable("import os, signal\nos.kill(os.getpid(), signal.SIGTERM)")
    result = run_native_tests(binary, capture_xml=True)
    assert not result.successful
    assert "terminated by signal" in result.result_error


def test_concurrent_captures_are_isolated_and_cleaned(native_executable):
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path

    binary = native_executable("""import pathlib, sys
output = pathlib.Path(next(arg.split("xml:", 1)[1] for arg in sys.argv if arg.startswith("--gtest_output=")))
output.write_text('<testsuite name="Concurrent"><testcase name="Works" time="0.001"/></testsuite>')
print(output)
""")
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: run_native_tests(binary, capture_xml=True), range(3)))
    assert all(result.successful for result in results)
    assert len({result.stdout for result in results}) == 3
    assert all(not Path(result.stdout.strip()).parent.exists() for result in results)
    results[0].cases.clear()
    assert len(results[1].cases) == len(results[2].cases) == 1


def test_capture_timeout_cleans_temporary_directory(native_executable, tmp_path, monkeypatch):
    from hil_automation import native

    temporary_directory = native.tempfile.TemporaryDirectory
    monkeypatch.setattr(
        native.tempfile, "TemporaryDirectory",
        lambda **kwargs: temporary_directory(dir=tmp_path, **kwargs),
    )
    binary = native_executable("import time\ntime.sleep(30)")
    with pytest.raises(NativeExecutionError, match="timed out"):
        run_native_tests(binary, timeout=0.1, capture_xml=True)
    assert list(tmp_path.glob("hil-gtest-*")) == []


@pytest.mark.parametrize("xml", [None, "<invalid>"])
def test_missing_or_malformed_capture_cleans_temporary_directory(
    gtest_executable, tmp_path, monkeypatch, xml,
):
    from hil_automation import native

    temporary_directory = native.tempfile.TemporaryDirectory
    monkeypatch.setattr(
        native.tempfile, "TemporaryDirectory",
        lambda **kwargs: temporary_directory(dir=tmp_path, **kwargs),
    )
    result = run_native_tests(gtest_executable(xml), capture_xml=True)
    assert result.result_error
    assert list(tmp_path.glob("hil-gtest-*")) == []


@pytest.mark.parametrize("capture_xml", [False, True])
def test_native_filter_is_one_literal_argument_and_enables_capture(native_executable, capture_xml):
    import json

    binary = native_executable("""import json, pathlib, sys
output = pathlib.Path(next(arg.split("xml:", 1)[1] for arg in sys.argv if arg.startswith("--gtest_output=")))
output.write_text('<testsuite name="Native"><testcase name="Selected" time="0"/></testsuite>')
print(json.dumps(sys.argv[1:]))
""")
    pattern = "Suite.*:Other.Case-Suite.Excluded; echo not-a-shell"
    result = run_native_tests(binary, native_filter=pattern, capture_xml=capture_xml)
    arguments = json.loads(result.stdout)
    assert arguments[0] == f"--gtest_filter={pattern}"
    assert len(arguments) == 2
    assert arguments[1].startswith("--gtest_output=xml:")
    assert result.results_captured and result.successful
    assert result.cases[0].name == "Selected"


@pytest.mark.parametrize("pattern", ["", "   ", 1, True, [], b"Suite.*", "S.\x00", "S.\n", "S.\r", "S.\x7f"])
def test_native_filter_rejects_invalid_values_before_execution(tmp_path, pattern):
    with pytest.raises(ValueError, match="Native filter must be a non-empty string"):
        run_native_tests(tmp_path / "missing", native_filter=pattern)


@pytest.mark.parametrize("arguments", [("--gtest_filter=Other.*",), ("--gtest_filter", "Other.*")])
def test_native_filter_cannot_conflict_with_manual_arguments(tmp_path, arguments):
    with pytest.raises(ValueError, match="filter only once"):
        run_native_tests(tmp_path / "missing", native_filter="Suite.*", arguments=arguments)


def test_native_filter_no_matches_is_not_successful(gtest_executable):
    binary = gtest_executable('<testsuites tests="0"/>')
    filtered = run_native_tests(binary, native_filter="Missing.*")
    assert filtered.exit_code == 0
    assert not filtered.successful
    assert filtered.result_error == "Native filter matched no tests: 'Missing.*'"
    assert filtered.cases == []
    unfiltered = run_native_tests(binary, capture_xml=True)
    assert unfiltered.successful
    assert unfiltered.result_error is None
