"""Execute YAML steps against a bench and collect structured results."""
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
import platform
from time import perf_counter
from uuid import uuid4

from .bench import Bench, SimulatedBench
from .config import Suite, TestCase
from .native_results import NativeCaseResult


class SimulatedAssertionFailure(AssertionError):
    """An expected simulated bench assertion failed."""


class SimulatedConnectionFailure(SimulatedAssertionFailure):
    """A heartbeat check failed on the simulated bench."""


@dataclass
class StepResult:
    index: int
    action: str
    status: str
    details: str
    duration_ms: float = 0.0
    failure_category: str | None = None


@dataclass
class AttemptResult:
    number: int
    status: str
    duration_ms: float
    details: str
    steps: list[StepResult] = field(default_factory=list)
    failure_category: str | None = None
    retryable: bool = False


@dataclass
class CaseResult:
    name: str
    status: str
    duration_ms: float
    details: str
    steps: list[StepResult] = field(default_factory=list)
    failure_category: str | None = None
    attempts: list[AttemptResult] = field(default_factory=list)

    @property
    def retry_count(self) -> int:
        return max(0, len(self.attempts) - 1)

    @property
    def passed_after_retry(self) -> bool:
        return self.status == "passed" and self.retry_count > 0


@dataclass
class RunReport:
    suite: str
    started_at: str
    passed: int
    failed: int
    results: list[CaseResult]
    finished_at: str = ""
    run_id: str = field(default_factory=lambda: str(uuid4()))
    schema_version: str = "1.0"
    duration_ms: float = 0.0
    skipped: int = 0
    native_results: list[NativeCaseResult] = field(default_factory=list)
    native_exit_code: int | None = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        for case, item in zip(self.results, payload["results"]):
            item["retry_count"] = case.retry_count
            item["passed_after_retry"] = case.passed_after_retry
        payload["metadata"] = {
            "python_version": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
        steps = [step for case in self.results for step in case.steps]
        payload["statistics"] = {
            "total_cases": len(self.results) + len(self.native_results),
            "passed_cases": self.passed,
            "failed_cases": self.failed,
            "skipped_cases": (
                sum(case.status == "skipped" for case in self.results)
                + sum(case.status in ("skipped", "disabled") for case in self.native_results)
            ),
            "duration_ms": self.duration_ms,
            "total_steps": len(steps),
            "executed_steps": sum(step.status != "skipped" for step in steps),
            "passed_steps": sum(step.status == "passed" for step in steps),
            "failed_steps": sum(step.status == "failed" for step in steps),
            "skipped_steps": sum(step.status == "skipped" for step in steps),
        }
        actions: dict[str, dict[str, int]] = {}
        for step in steps:
            if step.status == "skipped":
                continue
            counts = actions.setdefault(step.action, {"executed": 0, "passed": 0, "failed": 0})
            counts["executed"] += 1
            counts[step.status] += 1
        payload["action_statistics"] = actions
        return payload


def execute_step(bench: Bench, step: dict) -> None:
    action = step["action"]
    if action == "set_voltage":
        bench.set_voltage(float(step["value"]))
    elif action == "set_temperature":
        bench.set_temperature(step["value"])
    elif action == "expect_voltage":
        actual = bench.read_voltage()
        expected, tolerance = float(step["value"]), float(step["tolerance"])
        if abs(actual - expected) > tolerance:
            raise SimulatedAssertionFailure(f"Voltage {actual:.2f} V, expected {expected:.2f} ± {tolerance:.2f} V")
    elif action == "expect_temperature_below":
        actual = bench.read_temperature_c()
        limit = float(step["limit_c"])
        if not actual < limit:
            raise SimulatedAssertionFailure(
                f"Temperature {actual:.1f} °C is not below limit {limit:.1f} °C"
            )
    elif action == "set_connection":
        bench.set_connected(step["connected"])
    elif action == "expect_heartbeat":
        if not bench.heartbeat_ok():
            raise SimulatedConnectionFailure("Device heartbeat not detected; expected an active connection")
    else:
        raise ValueError(f"Unsupported action: {action}")


def make_bench(config: dict) -> SimulatedBench:
    return SimulatedBench(
        voltage=float(config.get("initial_voltage", 0)),
        temperature_c=config.get("temperature_c", 28),
        connected=config.get("connected", True),
    )


def _run_attempt(suite: Suite, test: TestCase, number: int) -> AttemptResult:
    bench = make_bench(suite.bench)
    started = perf_counter()
    status, details, category, retryable = "passed", "All steps passed", None, False
    steps: list[StepResult] = []
    for index, step in enumerate(test.steps, start=1):
        if status == "failed":
            steps.append(StepResult(index, step["action"], "skipped", "Earlier step failed"))
            continue
        step_started = perf_counter()
        try:
            execute_step(bench, step)
            steps.append(StepResult(index, step["action"], "passed", "Step passed"))
        except (AssertionError, ValueError) as exc:
            category = (
                "simulated_connection_failure" if isinstance(exc, SimulatedConnectionFailure)
                else "assertion_failure" if isinstance(exc, AssertionError)
                else "invalid_test_configuration"
            )
            retryable = isinstance(exc, SimulatedAssertionFailure)
            steps.append(StepResult(index, step["action"], "failed", str(exc), failure_category=category))
            status, details = "failed", f"Step {index}: {exc}"
        steps[-1].duration_ms = round((perf_counter() - step_started) * 1000, 3)
    return AttemptResult(
        number, status, round((perf_counter() - started) * 1000, 3),
        details, steps, category, retryable,
    )


def run_suite(suite: Suite, *, fail_fast: bool = False) -> RunReport:
    """Run cases in order; each explicitly enabled retry uses a fresh bench."""
    suite_started = perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    results: list[CaseResult] = []
    stopped = False
    for test in suite.tests:
        if stopped:
            results.append(CaseResult(
                test.name, "skipped", 0.0, "Not executed after earlier case failed",
                [StepResult(index, step["action"], "skipped", "Fail-fast stopped execution")
                 for index, step in enumerate(test.steps, start=1)],
            ))
            continue
        attempts: list[AttemptResult] = []
        for number in range(1, test.retries + 2):
            attempt = _run_attempt(suite, test, number)
            attempts.append(attempt)
            if attempt.status == "passed" or not attempt.retryable:
                break
        final = attempts[-1]
        details = final.details
        if len(attempts) > 1:
            details = (
                f"Passed on attempt {len(attempts)} after retry" if final.status == "passed"
                else f"{final.details} ({len(attempts)} attempts exhausted)"
            )
        results.append(CaseResult(
            test.name, final.status, round(sum(item.duration_ms for item in attempts), 3),
            details, [replace(step) for step in final.steps], final.failure_category, attempts,
        ))
        stopped = fail_fast and final.status == "failed"
    return RunReport(
        suite.name, started_at,
        sum(result.status == "passed" for result in results),
        sum(result.status == "failed" for result in results), results,
        finished_at=datetime.now(timezone.utc).isoformat(),
        duration_ms=round((perf_counter() - suite_started) * 1000, 3),
        skipped=sum(result.status == "skipped" for result in results),
    )
