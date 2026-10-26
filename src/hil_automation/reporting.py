"""Serialize execution reports and replace output files atomically."""
import json
import os
from pathlib import Path
import tempfile
from xml.etree import ElementTree as ET

from .native import NativeResult
from .runner import CaseResult, RunReport


class ReportError(ValueError):
    """A report could not be serialized or saved."""


def _atomic_write(path: str | Path, content: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_json_report(report: RunReport, path: str | Path) -> None:
    try:
        content = json.dumps(report.to_dict(), indent=2, allow_nan=False) + "\n"
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReportError(f"Cannot serialize JSON report: {exc}") from exc
    try:
        _atomic_write(path, content)
    except (OSError, ValueError) as exc:
        raise ReportError(f"Cannot write JSON report to {str(path)!r}: {exc}") from exc


def _xml_text(value: str) -> str:
    """Replace characters XML 1.0 cannot represent; ElementTree escapes markup."""
    return "".join(
        char if (
            char in "\t\n\r" or "\u0020" <= char <= "\ud7ff"
            or "\ue000" <= char <= "\ufffd" or "\U00010000" <= char <= "\U0010ffff"
        ) else "\ufffd"
        for char in value
    )


def junit_xml(report: RunReport) -> str:
    """Render one JUnit testsuite; elapsed times use seconds as JUnit expects."""
    cases = [(report.suite, case) for case in report.results]
    cases.extend(
        (case.suite, CaseResult(
            case.name, "skipped" if case.status == "disabled" else case.status,
            case.duration_ms, case.details,
            failure_category="native_test_failure" if case.status == "failed" else None,
        ))
        for case in report.native_results
    )
    errors = sum(
        case.status == "failed" and case.failure_category == "invalid_test_configuration"
        for _, case in cases
    )
    root = ET.Element("testsuite", {
        "name": _xml_text(report.suite),
        "tests": str(len(cases)),
        "failures": str(sum(case.status == "failed" for _, case in cases) - errors),
        "errors": str(errors),
        "skipped": str(sum(case.status == "skipped" for _, case in cases)),
        "time": f"{report.duration_ms / 1000:.6f}",
        "timestamp": report.started_at,
        "id": report.run_id,
    })
    for suite_name, case in cases:
        element = ET.SubElement(root, "testcase", {
            "name": _xml_text(case.name),
            "classname": _xml_text(suite_name),
            "time": f"{case.duration_ms / 1000:.6f}",
        })
        if case.status == "failed":
            tag = "error" if case.failure_category == "invalid_test_configuration" else "failure"
            diagnostic = ET.SubElement(element, tag, {
                "message": _xml_text(case.details),
                "type": case.failure_category or "assertion_failure",
            })
            diagnostic.text = _xml_text(case.details)
        elif case.status == "skipped":
            ET.SubElement(element, "skipped", {"message": _xml_text(case.details)})
    return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"


def write_junit_report(report: RunReport, path: str | Path) -> None:
    try:
        content = junit_xml(report)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReportError(f"Cannot serialize JUnit XML report: {exc}") from exc
    try:
        _atomic_write(path, content)
    except (OSError, ValueError) as exc:
        raise ReportError(f"Cannot write JUnit XML report to {str(path)!r}: {exc}") from exc


def native_report(result: NativeResult) -> RunReport:
    """Adapt validated GoogleTest cases without changing Python case/step semantics."""
    if not result.results_captured:
        raise ReportError("Native XML capture is required to generate a structured report")
    if result.result_error is not None:
        raise ReportError(f"Cannot report incomplete native results: {result.result_error}")
    return RunReport(
        suite="native-tests", started_at=result.started_at,
        passed=sum(case.status == "passed" for case in result.cases),
        failed=sum(case.status == "failed" for case in result.cases),
        skipped=sum(case.status in ("skipped", "disabled") for case in result.cases),
        results=[], native_results=list(result.cases), native_exit_code=result.exit_code,
        duration_ms=result.duration_ms, finished_at=result.finished_at,
    )
