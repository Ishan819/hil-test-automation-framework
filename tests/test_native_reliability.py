from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from hil_automation import native


VALID_XML = '<testsuite name="Native"><testcase name="PassedBeforeTimeout" time="0"/></testsuite>'


def test_timeout_discards_even_valid_xml_and_retains_partial_diagnostics(monkeypatch):
    paths = []
    ticks = iter([10, 10.25])
    monkeypatch.setattr(native, "perf_counter", lambda: next(ticks))
    def timed_out(command, **kwargs):
        assert kwargs["shell"] is False
        output = Path(next(arg.split("xml:", 1)[1] for arg in command if arg.startswith("--gtest_output=")))
        output.write_text(VALID_XML)
        paths.append(output)
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output=b"partial\xff", stderr=b"diagnostic\n")
    monkeypatch.setattr(native.subprocess, "run", timed_out)
    with pytest.raises(native.NativeExecutionError, match="timed out") as raised:
        native.run_native_tests("unused", timeout=1, capture_xml=True)
    assert raised.value.stdout == "partial\ufffd"
    assert raised.value.stderr == "diagnostic\n"
    assert raised.value.duration_ms == 250
    assert not paths[0].parent.exists()


def test_terminated_process_never_accepts_previously_written_valid_xml(monkeypatch):
    paths = []
    def terminated(command, **kwargs):
        output = Path(next(arg.split("xml:", 1)[1] for arg in command if arg.startswith("--gtest_output=")))
        output.write_text(VALID_XML)
        paths.append(output)
        return SimpleNamespace(returncode=-15, stdout="partial", stderr="terminated")
    monkeypatch.setattr(native.subprocess, "run", terminated)
    result = native.run_native_tests("unused", capture_xml=True)
    assert not result.successful
    assert result.result_error == "Native test process terminated by signal 15"
    assert not paths[0].parent.exists()


def test_missing_executable_capture_cleans_temporary_directory(monkeypatch):
    paths = []
    def missing(command, **kwargs):
        output = Path(next(arg.split("xml:", 1)[1] for arg in command if arg.startswith("--gtest_output=")))
        paths.append(output)
        raise FileNotFoundError("missing")
    monkeypatch.setattr(native.subprocess, "run", missing)
    with pytest.raises(native.NativeExecutionError, match="not found"):
        native.run_native_tests("unused", capture_xml=True)
    assert not paths[0].parent.exists()


@pytest.mark.parametrize("verbose", [False, True])
def test_timeout_cli_never_writes_successful_report_or_overwrites_history(
    monkeypatch, tmp_path, capsys, verbose,
):
    from hil_automation import cli

    destination = tmp_path / "previous.json"
    destination.write_text("previous")
    def timeout(*args, **kwargs):
        raise native.NativeExecutionError(
            "Native test executable timed out", stdout="partial output\n",
            stderr="timeout diagnostic\n", duration_ms=10,
        )
    monkeypatch.setattr(cli, "run_native_tests", timeout)
    arguments = ["hil-run", "--native-tests", "unused", "--report", str(destination)]
    if verbose:
        arguments.append("--verbose")
    monkeypatch.setattr(sys, "argv", arguments)
    assert cli.main() == 2
    output = capsys.readouterr()
    assert "timed out" in output.err and "timeout diagnostic" in output.err
    assert ("partial output" in output.out) == verbose
    assert "passed" not in output.out
    assert destination.read_text() == "previous"
