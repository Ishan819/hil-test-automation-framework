import json
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "tools/benchmark_parallel.py"


def test_opt_in_benchmark_reports_real_measurements():
    result = subprocess.run([sys.executable, str(SCRIPT), "--suites", "2", "--steps", "4",
                             "--repeats", "2", "--workers", "2"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["workload"] == {"suites": 2, "steps_per_suite": 4, "repeats": 2}
    assert [item["workers"] for item in data["measurements"]] == [1, 2]
    for item in data["measurements"]:
        assert len(item["wall_seconds"]) == 2
        assert all(value >= 0 for value in item["wall_seconds"])
        assert min(item["wall_seconds"]) <= item["median_seconds"] <= max(item["wall_seconds"])
    assert "do not guarantee" in data["note"]


@pytest.mark.parametrize("flag, value", [("--workers", "9"), ("--workers", "1"),
                                         ("--suites", "0"), ("--steps", "-1"), ("--repeats", "0")])
def test_benchmark_rejects_invalid_arguments(flag, value):
    result = subprocess.run([sys.executable, str(SCRIPT), flag, value], capture_output=True, text=True)
    assert result.returncode == 2
    assert not result.stdout
