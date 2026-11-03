"""Acceptance policies for simulated software tests, separate from execution YAML."""
from dataclasses import dataclass
from pathlib import Path
import math

import yaml


@dataclass(frozen=True)
class QualificationPolicy:
    min_pass_percentage: float = 100.0
    max_failed_cases: int = 0
    allow_skipped: bool = False
    allow_recovered: bool = False

    def __post_init__(self) -> None:
        percentage = self.min_pass_percentage
        if (
            isinstance(percentage, bool) or not isinstance(percentage, (int, float))
            or not 0 <= percentage <= 100 or not math.isfinite(percentage)
        ):
            raise ValueError("min_pass_percentage must be a finite number between 0 and 100")
        if isinstance(self.max_failed_cases, bool) or not isinstance(self.max_failed_cases, int) or self.max_failed_cases < 0:
            raise ValueError("max_failed_cases must be a non-negative integer")
        for name in ("allow_skipped", "allow_recovered"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be true or false")


class _PolicyLoader(yaml.SafeLoader):
    """Reject duplicate settings rather than silently changing acceptance criteria."""


def _mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str):
            raise ValueError("Qualification policy fields must be strings")
        if key in result:
            raise ValueError("Duplicate qualification policy field")
        result[key] = loader.construct_object(value_node)
    return result


_PolicyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def load_policy(path: str | Path) -> QualificationPolicy:
    try:
        payload = yaml.load(Path(path).read_text(encoding="utf-8"), Loader=_PolicyLoader)
    except (yaml.YAMLError, UnicodeError) as exc:
        raise ValueError("Invalid qualification policy YAML") from exc
    if not isinstance(payload, dict):
        raise ValueError("Qualification policy must be a YAML mapping")
    fields = QualificationPolicy.__dataclass_fields__
    if set(payload) - set(fields):
        raise ValueError("Unsupported qualification policy fields")
    return QualificationPolicy(**payload)
