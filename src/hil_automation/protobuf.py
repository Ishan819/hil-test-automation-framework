"""Map HIL reports to the shared binary schema."""
from .proto import hil_results_pb2 as pb
from .runner import RunReport


class ProtobufError(ValueError):
    """Binary results are malformed or violate the application schema."""


_STATUSES = {"passed": pb.PASSED, "failed": pb.FAILED, "skipped": pb.SKIPPED, "disabled": pb.DISABLED}


def _status(value: str) -> int:
    try:
        return _STATUSES[value]
    except KeyError as exc:
        raise ProtobufError(f"Unsupported result status: {value}") from exc


def report_to_proto(report: RunReport) -> pb.RunResult:
    if report.native_results or report.native_exit_code is not None:
        raise ProtobufError("Native Protobuf mapping is not available yet")
    result = pb.RunResult(
        schema_version=1, run_id=report.run_id, suite=report.suite,
        started_at=report.started_at, finished_at=report.finished_at,
    )
    result.summary.CopyFrom(pb.RunSummary(
        total=len(report.results), passed=report.passed, failed=report.failed,
        skipped=report.skipped, duration_ms=report.duration_ms,
    ))
    for case in report.results:
        target = result.cases.add(
            suite=report.suite, name=case.name, status=_status(case.status),
            duration_ms=case.duration_ms, details=case.details,
            failure_category=case.failure_category or "", origin=pb.PYTHON,
        )
        for step in case.steps:
            target.steps.add(
                index=step.index, action=step.action, status=_status(step.status),
                duration_ms=step.duration_ms, details=step.details,
                failure_category=step.failure_category or "",
            )
    return result
