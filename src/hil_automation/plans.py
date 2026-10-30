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
    if set(payload) - {"plan", "suites"}:
        raise ValueError("Unsupported execution plan fields")
    name = payload.get("plan")
    entries = payload.get("suites")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("'plan' must be a non-empty string")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Plan 'suites' must be a non-empty list")
    suites = []
    seen: set[Path] = set()
    for entry in entries:
        if not isinstance(entry, str) or not entry.strip() or entry != entry.strip():
            raise ValueError("Plan suite paths must be non-empty strings")
        relative = Path(entry)
        if relative.is_absolute() or "\x00" in entry:
            raise ValueError("Plan suite paths must be relative file paths")
        target = (source.parent / relative).resolve()
        if target in seen:
            raise ValueError(f"Duplicate suite in plan: {entry}")
        seen.add(target)
        if not target.is_file():
            raise ValueError(f"Plan suite file does not exist: {entry}")
        try:
            suite = load_suite(target)
        except (ValueError, OSError) as exc:
            raise ValueError(f"Invalid plan suite {entry!r}: {exc}") from exc
        suites.append(PlanSuite(target, suite))
    return ExecutionPlan(name, suites)
