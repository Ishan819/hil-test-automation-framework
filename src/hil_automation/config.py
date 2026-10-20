"""Safely load and validate suites described in YAML."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class TestCase:
    name: str
    steps: list[dict[str, Any]]


@dataclass(frozen=True)
class Suite:
    name: str
    bench: dict[str, Any]
    tests: list[TestCase]


# Defining actions centrally makes unrecognized steps fail before execution.
REQUIRED_PARAMS = {
    "set_voltage": ("value",),
    "expect_voltage": ("value", "tolerance"),
    "expect_temperature_below": ("limit_c",),
    "expect_heartbeat": (),
}


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def load_suite(path: str | Path) -> Suite:
    try:
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Suite must be a YAML mapping")
    name = payload.get("suite")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("'suite' must be a non-empty string")

    bench = payload.get("bench")
    if not isinstance(bench, dict) or bench.get("type") != "simulated":
        raise ValueError("v0.1 supports only bench.type: simulated")
    for key in ("initial_voltage", "temperature_c"):
        if key in bench and not _number(bench[key]):
            raise ValueError(f"bench.{key} must be a number")
    if "connected" in bench and not isinstance(bench["connected"], bool):
        raise ValueError("bench.connected must be true or false")
    initial_voltage = bench.get("initial_voltage", 0.0)
    if not 0 <= initial_voltage <= 24:
        raise ValueError("bench.initial_voltage must be between 0 and 24 V")

    raw_tests = payload.get("tests")
    if not isinstance(raw_tests, list) or not raw_tests:
        raise ValueError("'tests' must be a non-empty list")

    tests: list[TestCase] = []
    seen_names: set[str] = set()
    for item in raw_tests:
        if not isinstance(item, dict):
            raise ValueError("Every test must be a mapping")
        test_name = item.get("name")
        if not isinstance(test_name, str) or not test_name.strip():
            raise ValueError("Every test needs a non-empty name")
        if test_name in seen_names:
            raise ValueError(f"Duplicate test name: {test_name}")
        seen_names.add(test_name)

        steps = item.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError(f"Test '{test_name}' needs at least one step")
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict) or step.get("action") not in REQUIRED_PARAMS:
                raise ValueError(f"Unknown action in test '{test_name}', step {index}")
            action = step["action"]
            for param in REQUIRED_PARAMS[action]:
                if not _number(step.get(param)):
                    raise ValueError(f"{test_name}: {action}.{param} must be a number")
            if action == "expect_voltage" and step["tolerance"] < 0:
                raise ValueError("Voltage tolerance cannot be negative")
            if action == "set_voltage" and not 0 <= step["value"] <= 24:
                raise ValueError("Voltage must be between 0 and 24 V")
        tests.append(TestCase(name=test_name, steps=steps))
    return Suite(name=name, bench=bench, tests=tests)
