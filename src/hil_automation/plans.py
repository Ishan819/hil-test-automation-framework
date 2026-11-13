"""Load small execution plans that reference existing YAML suites."""
from dataclasses import dataclass
from pathlib import Path

import yaml

from .yaml_loader import ExecutionLoader

from .config import Suite, load_suite


MAX_WORKERS = 8


def validate_workers(workers: int) -> int:
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= MAX_WORKERS:
        raise ValueError(f"Workers must be an integer between 1 and {MAX_WORKERS}")
    return workers


@dataclass(frozen=True)
class PlanSuite:
    path: Path
    suite: Suite


@dataclass(frozen=True)
class ExecutionPlan:
    name: str
    suites: list[PlanSuite]
    workers: int = 1

    def __post_init__(self):
        validate_workers(self.workers)


def load_plan(path: str | Path) -> ExecutionPlan:
    source = Path(path).resolve()
    try:
        payload = yaml.load(source.read_text(encoding="utf-8"), Loader=ExecutionLoader)
    except (yaml.YAMLError, UnicodeError) as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise ValueError("Invalid plan YAML" + location) from exc
    if not isinstance(payload, dict):
        raise ValueError("Plan must be a YAML mapping")
    if set(payload) - {"plan", "suites", "workers"}:
        raise ValueError("Unsupported execution plan fields")
    workers = validate_workers(payload.get("workers", 1))
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
    return ExecutionPlan(name, suites, workers)
