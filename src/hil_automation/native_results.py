"""Structured individual GoogleTest outcomes, independent of process execution."""
from dataclasses import dataclass


@dataclass(frozen=True)
class NativeCaseResult:
    suite: str
    name: str
    status: str
    duration_ms: float
    details: str = ""
