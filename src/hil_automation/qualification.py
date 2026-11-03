"""Evaluate completed simulated runs against policies and their expected inventory."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
import math
from uuid import UUID

from .config import Suite
from .orchestration import BatchReport, SuiteExecution
from .plans import ExecutionPlan
from .qualification_policy import QualificationPolicy
from .runner import AttemptResult, CaseResult, RunReport, StepResult


@dataclass(frozen=True)
class ObservedMetrics:
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    skipped_cases: int = 0
    recovered_cases: int = 0
    incomplete_cases: int = 0

    @property
    def pass_percentage(self) -> float:
        # Skipped and missing cases never improve the percentage.
        return 100 * self.passed_cases / self.total_cases if self.total_cases else 0.0


@dataclass(frozen=True)
class ExecutionReference:
    kind: str
    index: int
    run_id: str | None
    started_at: str | None
    finished_at: str | None


@dataclass(frozen=True)
class QualificationResult:
    policy: QualificationPolicy
    metrics: ObservedMetrics
    complete: bool
    issues: tuple[str, ...]
    references: tuple[ExecutionReference, ...]
    evaluated_at: str

    @property
    def criteria(self) -> tuple["CriterionOutcome", ...]:
        metrics, policy = self.metrics, self.policy
        percentage_ok = metrics.passed_cases * 100 >= Decimal(str(policy.min_pass_percentage)) * metrics.total_cases
        return (
            CriterionOutcome("complete_evidence", True, self.complete, self.complete,
                             "Execution evidence is incomplete or inconsistent"),
            CriterionOutcome("min_pass_percentage", policy.min_pass_percentage, metrics.pass_percentage,
                             percentage_ok, "Pass percentage is below the required minimum"),
            CriterionOutcome("max_failed_cases", policy.max_failed_cases, metrics.failed_cases,
                             metrics.failed_cases <= policy.max_failed_cases, "Failed cases exceed the allowed maximum"),
            CriterionOutcome("allow_skipped", policy.allow_skipped, metrics.skipped_cases,
                             policy.allow_skipped or metrics.skipped_cases == 0, "Skipped cases are not permitted"),
            CriterionOutcome("allow_recovered", policy.allow_recovered, metrics.recovered_cases,
                             policy.allow_recovered or metrics.recovered_cases == 0, "Cases passing after retries are not permitted"),
        )

    @property
    def qualified(self) -> bool:
        return all(criterion.passed for criterion in self.criteria)

    def to_dict(self) -> dict:
        """Export only validated IDs, timestamps, numeric observations and fixed diagnostics."""
        return {
            "schema_version": "1.0", "scope": "simulated_software_tests",
            "decision": "qualified" if self.qualified else "not_qualified",
            "qualified": self.qualified, "complete_evidence": self.complete,
            "evaluated_at": self.evaluated_at, "policy": asdict(self.policy),
            "observed": {**asdict(self.metrics), "pass_percentage": self.metrics.pass_percentage},
            "criteria": [{
                "name": item.name, "expected": item.expected, "observed": item.observed,
                "passed": item.passed, "reason": None if item.passed else item.failure_reason,
            } for item in self.criteria],
            "execution_references": [asdict(reference) for reference in self.references],
            "evidence_issues": list(self.issues),
            "failure_reasons": [item.failure_reason for item in self.criteria if not item.passed],
        }


@dataclass(frozen=True)
class CriterionOutcome:
    name: str
    expected: bool | int | float
    observed: bool | int | float
    passed: bool
    failure_reason: str


def _steps_match(steps, expected, status):
    if not isinstance(steps, list) or len(steps) != len(expected) or not steps:
        return False
    statuses = []
    for index, (step, configured) in enumerate(zip(steps, expected), start=1):
        if (
            not isinstance(step, StepResult) or type(step.index) is not int or step.index != index
            or step.action != configured.get("action") or not _duration(step.duration_ms)
            or step.status not in ("passed", "failed", "skipped")
        ):
            return False
        statuses.append(step.status)
    if status == "passed":
        return all(item == "passed" for item in statuses)
    if status == "skipped":
        return all(item == "skipped" for item in statuses)
    if status == "failed" and statuses.count("failed") == 1:
        failed = statuses.index("failed")
        return all(item == "passed" for item in statuses[:failed]) and all(item == "skipped" for item in statuses[failed + 1:])
    return False


def _case_evidence(case, test):
    if not _duration(case.duration_ms) or not isinstance(case.attempts, list):
        return False
    if not _steps_match(case.steps, test.steps, case.status):
        return False
    if case.status == "skipped":
        return not case.attempts and case.duration_ms == 0
    if not 1 <= len(case.attempts) <= test.retries + 1:
        return False
    for number, attempt in enumerate(case.attempts, start=1):
        if (
            not isinstance(attempt, AttemptResult) or type(attempt.number) is not int
            or attempt.number != number or not _duration(attempt.duration_ms)
            or type(attempt.retryable) is not bool
            or not _steps_match(attempt.steps, test.steps, attempt.status)
        ):
            return False
        if number < len(case.attempts) and (
            attempt.status != "failed" or not attempt.retryable
            or attempt.failure_category not in ("assertion_failure", "simulated_connection_failure")
        ):
            return False
    final = case.attempts[-1]
    return (
        final.status == case.status and final.steps == case.steps
        and final.failure_category == case.failure_category
        and case.duration_ms == round(sum(item.duration_ms for item in case.attempts), 3)
    )


def _duration(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value < math.inf


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone(timezone.utc) if parsed.utcoffset() is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _reference(report, kind, index, seen, issues):
    run_id = None
    try:
        run_id = str(UUID(report.run_id))
    except (ValueError, TypeError, AttributeError):
        issues.append("invalid_run_id")
    if run_id is not None:
        if run_id in seen:
            issues.append("duplicate_run_id")
        seen.add(run_id)
    started, finished = _timestamp(report.started_at), _timestamp(report.finished_at)
    if started is None or finished is None or finished < started or not _duration(report.duration_ms):
        issues.append("invalid_execution_timing")
    return ExecutionReference(
        kind, index, run_id, started.isoformat() if started else None,
        finished.isoformat() if finished else None,
    )


def _suite_metrics(report, expected, index, seen, issues, references):
    total = len(expected.tests)
    if not total or expected.bench.get("type", "simulated") != "simulated":
        issues.append("invalid_simulated_inventory")
    if not isinstance(report, RunReport):
        issues.append("missing_suite_report")
        return ObservedMetrics(total_cases=total, incomplete_cases=total)
    references.append(_reference(report, "suite", index, seen, issues))
    if report.suite != expected.name or report.native_results or report.native_exit_code is not None:
        issues.append("suite_identity_or_origin_mismatch")
    cases = report.results if isinstance(report.results, list) else []
    if len(cases) != total or len({test.name for test in expected.tests}) != total:
        issues.append("case_inventory_mismatch")
    passed = failed = skipped = recovered = incomplete = 0
    for position, test in enumerate(expected.tests):
        case = cases[position] if position < len(cases) else None
        if not isinstance(case, CaseResult) or case.name != test.name:
            incomplete += 1
            issues.append("missing_or_misassociated_case")
            continue
        if case.status not in ("passed", "failed", "skipped"):
            incomplete += 1
            issues.append("unknown_case_status")
            continue
        if not _case_evidence(case, test):
            incomplete += 1
            issues.append("inconsistent_case_or_retry_evidence")
            continue
        passed += case.status == "passed"
        failed += case.status == "failed"
        skipped += case.status == "skipped"
        recovered += case.status == "passed" and len(case.attempts) > 1
    observed = tuple(sum(isinstance(case, CaseResult) and case.status == status for case in cases)
                     for status in ("passed", "failed", "skipped"))
    counts = (report.passed, report.failed, report.skipped)
    if any(type(count) is not int or count < 0 for count in counts) or counts != observed:
        issues.append("suite_summary_mismatch")
    return ObservedMetrics(total, passed, failed, skipped, recovered, incomplete)


def evaluate_qualification(
    result: RunReport | BatchReport | None, policy: QualificationPolicy, *,
    expected: Suite | ExecutionPlan | None = None,
) -> QualificationResult:
    """Require the original inventory; missing evidence always prevents qualification."""
    if not isinstance(policy, QualificationPolicy):
        raise ValueError("A validated qualification policy is required")
    issues, references, seen, observations = [], [], set(), []
    if isinstance(expected, Suite):
        observations.append(_suite_metrics(result, expected, 1, seen, issues, references))
    elif isinstance(expected, ExecutionPlan):
        if isinstance(result, BatchReport):
            references.append(_reference(result, "batch", 0, seen, issues))
            executions = result.suites if isinstance(result.suites, list) else []
            if result.plan != expected.name or len(executions) != len(expected.suites):
                issues.append("batch_inventory_mismatch")
        else:
            executions = []
            issues.append("missing_batch_report")
        for index, entry in enumerate(expected.suites, start=1):
            execution = executions[index - 1] if index <= len(executions) else None
            report = None
            if isinstance(execution, SuiteExecution):
                if execution.name != entry.suite.name or type(execution.case_count) is not int or execution.case_count != len(entry.suite.tests):
                    issues.append("planned_suite_mismatch")
                if execution.error is not None:
                    issues.append("worker_failure")
                report = execution.report
            observations.append(_suite_metrics(report, entry.suite, index, seen, issues, references))
    else:
        issues.append("missing_expected_inventory")
    metrics = ObservedMetrics(**{
        name: sum(getattr(item, name) for item in observations)
        for name in ObservedMetrics.__dataclass_fields__
    })
    if not metrics.total_cases:
        issues.append("empty_execution_evidence")
    return QualificationResult(
        policy, metrics, not issues and metrics.incomplete_cases == 0,
        tuple(dict.fromkeys(issues)), tuple(references), datetime.now(timezone.utc).isoformat(),
    )
