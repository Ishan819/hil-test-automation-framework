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

    def to_dict(self) -> dict:
        passed = sum(suite.report.passed for suite in self.suites if suite.report)
        failed = sum(suite.report.failed for suite in self.suites if suite.report)
        skipped = sum(
            suite.report.skipped if suite.report else suite.case_count for suite in self.suites
        )
        return {
            "schema_version": "1.0", "plan": self.plan, "run_id": self.run_id,
            "status": self.status, "started_at": self.started_at, "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "statistics": {
                "total_suites": len(self.suites),
                "executed_suites": sum(suite.report is not None for suite in self.suites),
                "passed_suites": sum(suite.status == "passed" for suite in self.suites),
                "failed_suites": sum(suite.status == "failed" for suite in self.suites),
                "skipped_suites": sum(suite.status == "skipped" for suite in self.suites),
                "total_cases": sum(suite.case_count for suite in self.suites),
                "executed_cases": passed + failed,
                "passed_cases": passed, "failed_cases": failed, "skipped_cases": skipped,
            },
            "suites": [{
                "suite": suite.name, "status": suite.status, "duration_ms": suite.duration_ms,
                "planned_cases": suite.case_count,
                "report": suite.report.to_dict() if suite.report else None,
            } for suite in self.suites],
        }


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


def write_batch_report(batch: BatchReport, directory: str, report_format: str = "json"):
    """Write each suite in a fresh batch directory; publish the JSON manifest last."""
    import json
    from pathlib import Path
    from .reporting import (
        ReportError, _atomic_write, write_json_report, write_junit_report, write_protobuf_report,
    )

    writers = {
        "json": ("json", write_json_report),
        "junit": ("xml", write_junit_report),
        "protobuf": ("pb", write_protobuf_report),
    }
    if report_format not in writers:
        raise ReportError(f"Unsupported batch report format: {report_format}")
    extension, write = writers[report_format]
    destination = Path(directory) / batch.run_id
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.mkdir(exist_ok=False)
        payload = batch.to_dict()
        for index, (suite, item) in enumerate(zip(batch.suites, payload["suites"]), start=1):
            item["report_file"] = None
            if suite.report is not None:
                filename = f"{index:03d}.{extension}"
                write(suite.report, destination / filename)
                item["report_file"] = filename
        manifest = destination / "batch.json"
        _atomic_write(manifest, json.dumps(payload, indent=2, allow_nan=False) + "\n")
        return manifest
    except (OSError, ValueError) as exc:
        raise ReportError(f"Cannot write batch report: {exc}") from exc
