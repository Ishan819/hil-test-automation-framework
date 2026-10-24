"""Execute YAML steps against a bench and collect structured results."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import platform
from time import perf_counter
from uuid import uuid4

from .bench import Bench, SimulatedBench
from .config import Suite


@dataclass
class StepResult:
    index: int
    action: str
    status: str
    details: str
    duration_ms: float = 0.0


@dataclass
class CaseResult:
    name: str
    status: str
    duration_ms: float
    details: str
    steps: list[StepResult] = field(default_factory=list)


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

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["metadata"] = {
            "python_version": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
        steps = [step for case in self.results for step in case.steps]
        payload["statistics"] = {
            "total_cases": len(self.results),
            "passed_cases": self.passed,
            "failed_cases": self.failed,
            "skipped_cases": sum(case.status == "skipped" for case in self.results),
            "duration_ms": self.duration_ms,
            "total_steps": len(steps),
            "executed_steps": sum(step.status != "skipped" for step in steps),
            "passed_steps": sum(step.status == "passed" for step in steps),
            "failed_steps": sum(step.status == "failed" for step in steps),
            "skipped_steps": sum(step.status == "skipped" for step in steps),
        }
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
            raise AssertionError(f"Voltage {actual:.2f} V, expected {expected:.2f} ± {tolerance:.2f} V")
    elif action == "expect_temperature_below":
        actual = bench.read_temperature_c()
        limit = float(step["limit_c"])
        if not actual < limit:
            raise AssertionError(
                f"Temperature {actual:.1f} °C is not below limit {limit:.1f} °C"
            )
    elif action == "set_connection":
        bench.set_connected(step["connected"])
    elif action == "expect_heartbeat":
        if not bench.heartbeat_ok():
            raise AssertionError("Device heartbeat not detected; expected an active connection")
    else:
        raise ValueError(f"Unsupported action: {action}")


def make_bench(config: dict) -> SimulatedBench:
    return SimulatedBench(
        voltage=float(config.get("initial_voltage", 0)),
        temperature_c=config.get("temperature_c", 28),
        connected=config.get("connected", True),
    )


def run_suite(suite: Suite) -> RunReport:
    """Give each test a fresh bench so tests cannot leak state into one another."""
    suite_started = perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    results: list[CaseResult] = []
    for test in suite.tests:
        bench = make_bench(suite.bench)
        started = perf_counter()
        status, details = "passed", "All steps passed"
        steps: list[StepResult] = []
        for index, step in enumerate(test.steps, start=1):
            if status == "failed":
                steps.append(StepResult(
                    index, step["action"], "skipped", "Earlier step failed",
                ))
                continue
            step_started = perf_counter()
            try:
                execute_step(bench, step)
                steps.append(StepResult(index, step["action"], "passed", "Step passed"))
            except (AssertionError, ValueError) as exc:
                steps.append(StepResult(index, step["action"], "failed", str(exc)))
                status, details = "failed", f"Step {index}: {exc}"
            steps[-1].duration_ms = round((perf_counter() - step_started) * 1000, 3)
        results.append(
            CaseResult(test.name, status, round((perf_counter() - started) * 1000, 3), details, steps)
        )
    passed = sum(result.status == "passed" for result in results)
    return RunReport(
        suite.name, started_at, passed, len(results) - passed, results,
        finished_at=datetime.now(timezone.utc).isoformat(),
        duration_ms=round((perf_counter() - suite_started) * 1000, 3),
    )
