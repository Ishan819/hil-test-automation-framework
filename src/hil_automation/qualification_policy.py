"""Acceptance policies for simulated software tests, separate from execution YAML."""
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class QualificationPolicy:
    min_pass_percentage: float = 100.0
    max_failed_cases: int = 0
    allow_skipped: bool = False
    allow_recovered: bool = False


def load_policy(path: str | Path) -> QualificationPolicy:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Qualification policy must be a YAML mapping")
    fields = QualificationPolicy.__dataclass_fields__
    if set(payload) - set(fields):
        raise ValueError("Unsupported qualification policy fields")
    return QualificationPolicy(**payload)
