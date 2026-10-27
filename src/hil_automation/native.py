"""Run native test executables as separate processes, without shared bench state."""
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import math
from pathlib import Path
import subprocess
import tempfile
from time import perf_counter
from typing import Sequence

from .native_results import NativeCaseResult, NativeResultError, parse_gtest_xml


class NativeExecutionError(RuntimeError):
    """A native test process could not be started or completed in time."""


@dataclass(frozen=True)
class NativeResult:
    executable: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    cases: list[NativeCaseResult] = field(default_factory=list)
    results_captured: bool = False
    started_at: str = ""
    finished_at: str = ""
    result_error: str | None = None

    @property
    def successful(self) -> bool:
        return (
            self.exit_code == 0 and self.result_error is None
            and not any(case.status == "failed" for case in self.cases)
        )


def run_native_tests(
    executable: str | Path, *, timeout: float = 30.0, arguments: Sequence[str] = (),
    capture_xml: bool = False, native_filter: str | None = None,
) -> NativeResult:
    """Execute a binary directly; nonzero test exits are results, not launch errors."""
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ValueError("Native timeout must be a finite positive number of seconds")
    try:
        seconds = float(timeout)
    except OverflowError as exc:
        raise ValueError("Native timeout must be a finite positive number of seconds") from exc
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Native timeout must be a finite positive number of seconds")

    if native_filter is not None:
        if (
            not isinstance(native_filter, str) or not native_filter.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in native_filter)
        ):
            raise ValueError("Native filter must be a non-empty string without control characters")
        if any(arg == "--gtest_filter" or arg.startswith("--gtest_filter=") for arg in arguments):
            raise ValueError("Specify the native filter only once")
        arguments = [*arguments, f"--gtest_filter={native_filter}"]
        # Inspect actual outcomes even in otherwise raw mode; zero matches is an error.
        capture_xml = True

    binary = Path(executable).expanduser().resolve()
    if not capture_xml:
        return _execute_native(binary, seconds, arguments)
    if any(argument.startswith("--gtest_output") for argument in arguments):
        raise ValueError("Structured capture manages --gtest_output automatically")
    with tempfile.TemporaryDirectory(prefix="hil-gtest-") as directory:
        output = Path(directory) / "results.xml"
        started_at = datetime.now(timezone.utc).isoformat()
        result = _execute_native(binary, seconds, [*arguments, f"--gtest_output=xml:{output}"])
        cases: list[NativeCaseResult] = []
        error = None
        try:
            cases = parse_gtest_xml(output)
        except NativeResultError as exc:
            error = str(exc)
        if result.exit_code < 0:
            error = f"Native test process terminated by signal {-result.exit_code}"
        elif error is None:
            failed = any(case.status == "failed" for case in cases)
            if result.exit_code == 0 and failed:
                error = "Native process exited successfully but GoogleTest XML reports failures"
            elif result.exit_code != 0 and not failed:
                error = f"Native process exited with code {result.exit_code} but XML reports no failures"
        if error is None and native_filter is not None and not cases:
            error = f"Native filter matched no tests: {native_filter!r}"
        return replace(
            result, cases=cases, results_captured=True, result_error=error,
            started_at=started_at, finished_at=datetime.now(timezone.utc).isoformat(),
        )


def _execute_native(binary: Path, seconds: float, arguments: Sequence[str]) -> NativeResult:
    started = perf_counter()
    try:
        finished = subprocess.run(
            [str(binary), *arguments], shell=False, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=seconds, check=False,
        )
    except FileNotFoundError as exc:
        raise NativeExecutionError(f"Native test executable not found: {binary}") from exc
    except subprocess.TimeoutExpired as exc:
        raise NativeExecutionError(
            f"Native test executable timed out after {seconds:g} seconds: {binary}"
        ) from exc
    except OSError as exc:
        raise NativeExecutionError(f"Cannot execute native test binary {binary}: {exc}") from exc
    return NativeResult(
        str(binary), finished.returncode, finished.stdout, finished.stderr,
        round((perf_counter() - started) * 1000, 3),
    )
