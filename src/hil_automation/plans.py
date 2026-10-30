"""Load small execution plans that reference existing YAML suites."""
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import Suite, load_suite


@dataclass(frozen=True)
class PlanSuite:
    path: Path
    suite: Suite


@dataclass(frozen=True)
class ExecutionPlan:
    name: str
    suites: list[PlanSuite]


def load_plan(path: str | Path) -> ExecutionPlan:
    source = Path(path).resolve()
    try:
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid plan YAML: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Plan must be a YAML mapping")
    name = payload.get("plan")
    entries = payload.get("suites")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("'plan' must be a non-empty string")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Plan 'suites' must be a non-empty list")
    suites = []
    for entry in entries:
        target = (source.parent / entry).resolve()
        suites.append(PlanSuite(target, load_suite(target)))
    return ExecutionPlan(name, suites)
