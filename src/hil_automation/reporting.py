"""Serialize execution reports and replace output files atomically."""
import json
import os
from pathlib import Path
import tempfile

from .runner import RunReport


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
    content = json.dumps(report.to_dict(), indent=2, allow_nan=False) + "\n"
    _atomic_write(path, content)
