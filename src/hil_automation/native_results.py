"""Structured individual GoogleTest outcomes, independent of process execution."""
from dataclasses import dataclass
import math
from pathlib import Path
from xml.etree import ElementTree as ET


@dataclass(frozen=True)
class NativeCaseResult:
    suite: str
    name: str
    status: str
    duration_ms: float
    details: str = ""


class NativeResultError(ValueError):
    """A GoogleTest report cannot be interpreted reliably."""


def parse_gtest_xml(path: str | Path) -> list[NativeCaseResult]:
    """Read GoogleTest testsuites/testsuite XML; durations are converted to ms."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise NativeResultError(f"Cannot read GoogleTest XML: {exc}") from exc
    if root.tag not in ("testsuites", "testsuite"):
        raise NativeResultError("GoogleTest XML root must be testsuites or testsuite")
    _validate_counts(root)
    cases: list[NativeCaseResult] = []
    seen: set[tuple[str, str]] = set()
    for suite in root.iter("testsuite"):
        for case in suite.findall("testcase"):
            suite_name = case.get("classname") or suite.get("name", "")
            name = case.get("name", "")
            if not suite_name.strip() or not name.strip():
                raise NativeResultError("GoogleTest cases need a suite name and test name")
            identity = (suite_name, name)
            if identity in seen:
                raise NativeResultError(f"Duplicate GoogleTest case: {suite_name}.{name}")
            seen.add(identity)
            execution = case.get("status", "run")
            outcome = case.get("result", "suppressed" if execution == "notrun" else "completed")
            if execution not in ("run", "notrun") or outcome not in (
                "completed", "skipped", "suppressed",
            ):
                raise NativeResultError(f"Unknown GoogleTest outcome for {suite_name}.{name}")
            diagnostics = case.findall("failure") + case.findall("error")
            skipped = case.find("skipped")
            if diagnostics:
                status = "failed"
                details = "\n".join(_diagnostic(item) for item in diagnostics)
            elif execution == "notrun":
                status, details = "disabled", "Disabled in GoogleTest"
            elif skipped is not None or outcome == "skipped":
                status = "skipped"
                details = _diagnostic(skipped) if skipped is not None else "Skipped in GoogleTest"
            elif outcome == "suppressed":
                raise NativeResultError(f"Incomplete GoogleTest outcome for {suite_name}.{name}")
            else:
                status, details = "passed", ""
            try:
                default_time = "0" if status in ("skipped", "disabled") else None
                duration_ms = float(case.get("time", default_time)) * 1000
            except (TypeError, ValueError, OverflowError) as exc:
                raise NativeResultError(f"Invalid GoogleTest duration for {suite_name}.{name}") from exc
            if not math.isfinite(duration_ms) or duration_ms < 0:
                raise NativeResultError(f"Invalid GoogleTest duration for {suite_name}.{name}")
            cases.append(NativeCaseResult(suite_name, name, status, duration_ms, details))
    if len(cases) != sum(1 for _ in root.iter("testcase")):
        raise NativeResultError("GoogleTest cases must belong directly to a testsuite")
    return cases


def _diagnostic(element: ET.Element) -> str:
    message = element.get("message", "").strip()
    body = "".join(element.itertext()).strip()
    return "\n".join(dict.fromkeys(value for value in (message, body) if value)) or "No diagnostic provided"


def _validate_counts(root: ET.Element) -> None:
    for element in root.iter():
        if element.tag not in ("testsuites", "testsuite"):
            continue
        cases = list(element.iter("testcase"))
        observed = {
            "tests": len(cases),
            "failures": sum(case.find("failure") is not None for case in cases),
            "errors": sum(case.find("error") is not None for case in cases),
            "disabled": sum(case.get("status") == "notrun" for case in cases),
            "skipped": sum(
                case.get("status") != "notrun" and (
                    case.get("result") == "skipped" or case.find("skipped") is not None
                ) for case in cases
            ),
        }
        if element is root and not cases and "tests" not in element.attrib:
            raise NativeResultError("Empty GoogleTest XML must declare tests=0")
        for key, expected in observed.items():
            if key not in element.attrib:
                continue
            try:
                reported = int(element.attrib[key])
            except ValueError as exc:
                raise NativeResultError(f"Invalid GoogleTest {key} count") from exc
            if reported != expected:
                raise NativeResultError(
                    f"Incomplete GoogleTest XML: {key} count {reported}, found {expected}"
                )
