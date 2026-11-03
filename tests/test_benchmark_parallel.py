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


@pytest.mark.parametrize("flag,value", [("--warmups", "-1"), ("--warmups", "11"),
    ("--suites", "129"), ("--steps", "100001"), ("--repeats", "101")])
def test_benchmark_bounds(flag, value):
    result = subprocess.run([sys.executable, str(SCRIPT), flag, value], capture_output=True)
    assert result.returncode == 2


def load_benchmark():
    import importlib.util
    spec = importlib.util.spec_from_file_location("benchmark", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_measure_uses_fresh_real_execution_and_clock(monkeypatch):
    benchmark = load_benchmark()
    original = benchmark.run_plan
    observed = []
    def run(plan, **kwargs):
        batch = original(plan, **kwargs)
        observed.append((plan, batch))
        return batch
    monkeypatch.setattr(benchmark, "run_plan", run)
    ticks = iter([1, 1.25, 2, 2.5])
    monkeypatch.setattr(benchmark, "perf_counter", lambda: next(ticks))
    # Synthetic clock fixture verifies accounting, not performance.
    assert benchmark.measure(2, 4, 1) == .25
    assert benchmark.measure(2, 4, 2) == .5
    assert observed[0][0] == observed[1][0]
    assert observed[0][0] is not observed[1][0]
    assert len({suite.report.run_id for _, batch in observed for suite in batch.suites}) == 4


def test_measure_rejects_incomplete_execution(monkeypatch):
    from types import SimpleNamespace
    benchmark = load_benchmark()
    monkeypatch.setattr(benchmark, "run_plan", lambda *a, **k: SimpleNamespace(status="failed", suites=[]))
    with pytest.raises(RuntimeError, match="did not complete"):
        benchmark.measure(2, 4, 2)


def test_statistics_and_small_sample_percentile():
    stats = load_benchmark().statistics([4, 1, 2, 3], 5)
    assert stats == {"median_seconds": 2.5, "min_seconds": 1, "max_seconds": 4,
                     "mean_seconds": 2.5, "speedup": 2}
    assert load_benchmark().statistics([0], 1)["speedup"] is None


def test_p95_nearest_rank_requires_twenty_samples():
    stats = load_benchmark().statistics
    assert "p95_seconds" not in stats(list(range(1, 20)), 1)
    assert stats(list(range(20, 0, -1)), 1)["p95_seconds"] == 19
