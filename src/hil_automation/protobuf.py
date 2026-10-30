"""Map HIL reports to the shared binary schema."""
import json
import math

from .proto import hil_results_pb2 as pb
from .runner import RunReport


class ProtobufError(ValueError):
    """Binary results are malformed or violate the application schema."""


MAX_PAYLOAD_BYTES = 16 * 1024 * 1024


_STATUSES = {"passed": pb.PASSED, "failed": pb.FAILED, "skipped": pb.SKIPPED, "disabled": pb.DISABLED}


def _status(value: str) -> int:
    try:
        return _STATUSES[value]
    except KeyError as exc:
        raise ProtobufError(f"Unsupported result status: {value}") from exc


def report_to_proto(report: RunReport) -> pb.RunResult:
    result = pb.RunResult(
        schema_version=1, run_id=report.run_id, suite=report.suite,
        started_at=report.started_at, finished_at=report.finished_at,
    )
    result.summary.CopyFrom(pb.RunSummary(
        total=len(report.results) + len(report.native_results), passed=report.passed, failed=report.failed,
        skipped=report.skipped, duration_ms=report.duration_ms,
    ))
    for case in report.results:
        target = result.cases.add(
            suite=report.suite, name=case.name, status=_status(case.status),
            duration_ms=case.duration_ms, details=case.details,
            failure_category=case.failure_category or "", origin=pb.PYTHON,
        )
        if case.retry_count:
            target.details += "\nRetry history: " + json.dumps(case.history_dict(), allow_nan=False)
        for step in case.steps:
            target.steps.add(
                index=step.index, action=step.action, status=_status(step.status),
                duration_ms=step.duration_ms, details=step.details,
                failure_category=step.failure_category or "",
            )
    for case in report.native_results:
        result.cases.add(
            suite=case.suite, name=case.name, status=_status(case.status),
            duration_ms=case.duration_ms, details=case.details, origin=pb.NATIVE,
            failure_category="native_test_failure" if case.status == "failed" else "",
        )
    if report.native_exit_code is not None:
        result.native_exit_code = report.native_exit_code
    validate_result(result)
    return result


def serialize_result(message: pb.RunResult) -> bytes:
    if not isinstance(message, pb.RunResult):
        raise ProtobufError("Expected a RunResult message")
    validate_result(message)
    payload = message.SerializeToString(deterministic=True)
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ProtobufError("Protobuf payload exceeds 16 MiB")
    return payload


def parse_result(payload: bytes) -> pb.RunResult:
    from google.protobuf.message import DecodeError

    if not isinstance(payload, bytes):
        raise ProtobufError("Protobuf payload must be bytes")
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ProtobufError("Protobuf payload exceeds 16 MiB")
    message = pb.RunResult()
    try:
        message.ParseFromString(payload)
    except DecodeError as exc:
        raise ProtobufError("Malformed Protobuf result payload") from exc
    validate_result(message)
    return message


def validate_result(message: pb.RunResult) -> None:
    if message.schema_version != 1:
        raise ProtobufError("Unsupported Protobuf schema version")
    if not message.run_id.strip() or not message.suite.strip():
        raise ProtobufError("Run ID and suite name are required")
    if not message.HasField("summary"):
        raise ProtobufError("Run summary is required")
    _duration(message.summary.duration_ms)
    seen: set[tuple[int, str, str]] = set()
    passed = failed = skipped = 0
    for case in message.cases:
        if not case.name.strip() or not case.suite.strip():
            raise ProtobufError("Case and suite names are required")
        if case.origin not in (pb.PYTHON, pb.NATIVE):
            raise ProtobufError("Unsupported case origin")
        if case.status not in (pb.PASSED, pb.FAILED, pb.SKIPPED, pb.DISABLED):
            raise ProtobufError("Unsupported case status")
        if case.status == pb.DISABLED and case.origin != pb.NATIVE:
            raise ProtobufError("Only native cases can be disabled")
        identity = (case.origin, case.suite, case.name)
        if identity in seen:
            raise ProtobufError("Duplicate case identity")
        seen.add(identity)
        _duration(case.duration_ms)
        if case.status == pb.FAILED and not case.details.strip():
            raise ProtobufError("Failed cases require diagnostic details")
        for index, step in enumerate(case.steps, start=1):
            if step.index != index or not step.action.strip():
                raise ProtobufError("Step indices must be sequential and actions non-empty")
            if step.status not in (pb.PASSED, pb.FAILED, pb.SKIPPED):
                raise ProtobufError("Unsupported step status")
            if step.status == pb.FAILED and not step.details.strip():
                raise ProtobufError("Failed steps require diagnostic details")
            _duration(step.duration_ms)
        passed += case.status == pb.PASSED
        failed += case.status == pb.FAILED
        skipped += case.status in (pb.SKIPPED, pb.DISABLED)
    summary = message.summary
    if (summary.total, summary.passed, summary.failed, summary.skipped) != (
        len(message.cases), passed, failed, skipped,
    ):
        raise ProtobufError("Run summary does not match case outcomes")
    if message.HasField("native_exit_code"):
        native_failed = any(case.origin == pb.NATIVE and case.status == pb.FAILED for case in message.cases)
        if (message.native_exit_code == 0 and native_failed) or (
            message.native_exit_code != 0 and not native_failed
        ):
            raise ProtobufError("Native exit code does not match native outcomes")


def _duration(value: float) -> None:
    if not math.isfinite(value) or value < 0:
        raise ProtobufError("Durations must be finite and non-negative")
