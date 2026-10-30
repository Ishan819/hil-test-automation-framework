"""Execute validated plans sequentially with independent suite runs."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from .plans import ExecutionPlan
from .runner import RunReport, run_suite


@dataclass
class SuiteExecution:
    name: str
    case_count: int
    report: RunReport | None

    @property
    def status(self) -> str:
        return "skipped" if self.report is None else "failed" if self.report.failed else "passed"

    @property
    def duration_ms(self) -> float:
        return self.report.duration_ms if self.report else 0.0


@dataclass
class BatchReport:
    plan: str
    suites: list[SuiteExecution]
    started_at: str
    finished_at: str
    duration_ms: float
    run_id: str = field(default_factory=lambda: str(uuid4()))

    @property
    def status(self) -> str:
        return "failed" if any(suite.status == "failed" for suite in self.suites) else "passed"


def run_plan(plan: ExecutionPlan, *, fail_fast: bool = False) -> BatchReport:
    if not plan.suites:
        raise ValueError("Execution plan must contain at least one suite")
    started = perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    suites = []
    stopped = False
    for entry in plan.suites:
        report = None if stopped else run_suite(entry.suite, fail_fast=fail_fast)
        execution = SuiteExecution(entry.suite.name, len(entry.suite.tests), report)
        suites.append(execution)
        if fail_fast and execution.status == "failed":
            stopped = True
    return BatchReport(
        plan.name, suites, started_at, datetime.now(timezone.utc).isoformat(),
        round((perf_counter() - started) * 1000, 3),
    )
