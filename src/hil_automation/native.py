"""Run native test executables as separate processes, without shared bench state."""
from dataclasses import dataclass
import math
from pathlib import Path
import subprocess
from time import perf_counter
from typing import Sequence


class NativeExecutionError(RuntimeError):
    """A native test process could not be started or completed in time."""


@dataclass(frozen=True)
class NativeResult:
    executable: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float


def run_native_tests(
    executable: str | Path, *, timeout: float = 30.0, arguments: Sequence[str] = (),
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

    binary = Path(executable).expanduser().resolve()
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
