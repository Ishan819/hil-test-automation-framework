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
    cases: list[NativeCaseResult] = []
    for suite in root.iter("testsuite"):
        for case in suite.findall("testcase"):
            suite_name = case.get("classname") or suite.get("name", "")
            name = case.get("name", "")
            if not suite_name.strip() or not name.strip():
                raise NativeResultError("GoogleTest cases need a suite name and test name")
            try:
                duration_ms = float(case.attrib["time"]) * 1000
            except (KeyError, ValueError, OverflowError) as exc:
                raise NativeResultError(f"Invalid GoogleTest duration for {suite_name}.{name}") from exc
            if not math.isfinite(duration_ms) or duration_ms < 0:
                raise NativeResultError(f"Invalid GoogleTest duration for {suite_name}.{name}")
            if (
                case.get("status", "run") != "run"
                or case.get("result", "completed") != "completed"
                or case.find("failure") is not None or case.find("skipped") is not None
                or case.find("error") is not None
            ):
                raise NativeResultError("Unsupported GoogleTest outcome")
            cases.append(NativeCaseResult(suite_name, name, "passed", duration_ms))
    return cases
